import importlib.util
import io
import os
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[2]


def _workflow(name: str) -> dict:
    return yaml.load(
        (PROJECT_ROOT / ".github" / "workflows" / name).read_text(),
        Loader=yaml.BaseLoader,
    )


def _load_module(name: str, relative_path: str):
    path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_gate_covers_required_checks_and_triggers() -> None:
    workflow = _workflow("release-gate.yml")

    assert set(workflow["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert set(workflow["jobs"]) == {
        "quality",
        "agent-regression",
        "service-integration",
        "image",
    }
    image = workflow["jobs"]["image"]
    assert set(image["needs"]) == {"quality", "agent-regression", "service-integration"}
    assert image["permissions"]["attestations"] == "write"
    assert image["permissions"]["id-token"] == "write"
    assert image["permissions"]["packages"] == "write"
    workflow_text = (PROJECT_ROOT / ".github/workflows/release-gate.yml").read_text()
    for required_command in (
        "uv lock --check",
        "ruff check",
        "tests/unit tests/api",
        "alembic upgrade head",
        "alembic check",
        "test_release_services.py",
        "run_agentic_fault_evals.py",
        "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a",
    ):
        assert required_command in workflow_text
    assert "sha-${{ github.sha }}" in workflow_text
    assert "@main" not in workflow_text
    for image in ("postgres:16-alpine", "redis:7-alpine", "opensearchproject/opensearch:2.19.0"):
        assert f"{image}@sha256:" in workflow_text


def test_hosted_answer_gate_requires_manual_trigger_and_approval() -> None:
    workflow = _workflow("hosted-answer-gate.yml")
    assert set(workflow["on"]) == {"workflow_dispatch"}
    job = workflow["jobs"]["answer-regression"]
    assert job["environment"] == "staging-evaluation"
    workflow_text = (PROJECT_ROOT / ".github/workflows/hosted-answer-gate.yml").read_text()
    assert "--require-answer-approved" in workflow_text
    assert "runs-on: [self-hosted, staging]" in workflow_text
    assert "verify_release_candidate.py" in workflow_text
    assert "steps.manifest.outputs.answer_dataset_name" in workflow_text
    assert "production-agentic-rag-week7-answer-v0" not in workflow_text
    assert "langfuse/experiment-action@b945f9bf921b24a4074306078f621cba729d173e" in workflow_text
    assert "should_fail_on_regression: \"true\"" in workflow_text


def test_release_manifest_locks_datasets_and_versions(tmp_path: Path) -> None:
    validator = _load_module("release_manifest", "scripts/ci/validate_release_manifest.py")

    result = validator.validate()

    assert result["fault_items"] == 6
    assert result["answer_items"] == 7
    assert result["answer_review_status"] == "needs_human_review"
    with pytest.raises(ValueError, match="not approved"):
        validator.validate(require_answer_approved=True)

    github_output = tmp_path / "github-output"
    validator._write_github_output(github_output, result)
    exported = dict(
        line.split("=", 1)
        for line in github_output.read_text(encoding="utf-8").splitlines()
    )
    assert exported["answer_dataset_name"] == "production-agentic-rag-week7-answer-v0"
    assert exported["answer_dataset_timestamp"] == "2026-09-03T17:10:55.323Z"
    assert exported["model"] == "gpt-5.4-mini-2026-03-17"


def test_candidate_identity_requires_digest_and_full_commit() -> None:
    verifier = _load_module("candidate_verifier", "scripts/ci/verify_release_candidate.py")
    verifier.validate_identity(
        f"ghcr.io/example/rag@sha256:{'a' * 64}",
        "b" * 40,
    )

    with pytest.raises(ValueError, match="sha256 digest"):
        verifier.validate_identity("ghcr.io/example/rag:latest", "b" * 40)
    with pytest.raises(ValueError, match="40-character SHA"):
        verifier.validate_identity(f"ghcr.io/example/rag@sha256:{'a' * 64}", "deadbeef")


def test_candidate_verification_rejects_a_stale_deployment(monkeypatch) -> None:
    verifier = _load_module("candidate_version_verifier", "scripts/ci/verify_release_candidate.py")
    response = io.BytesIO(b'{"status":"ready","version":"old-commit"}')
    response.status = 200
    monkeypatch.setattr(verifier.urllib.request, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError, match="candidate version mismatch"):
        verifier.verify_deployment("https://rag.example.com", "secret-key", "a" * 40)


def test_answer_contract_evaluator_requires_grounded_fragments_and_citations() -> None:
    experiment = _load_module("answer_gate", "experiments/agentic_answer_gate.py")
    expected = {
        "http_status": 200,
        "business_status": "success",
        "required_answer_fragments": ["56.4"],
        "required_answer_any_groups": [["denoise", "diffusion process"]],
        "required_source_fragments": ["2508.11110"],
        "required_citation_ids": ["2508.11110"],
    }
    valid = {
        "http_status": 200,
        "payload": {
            "business_status": "success",
            "answer": "The diffusion process denoises code with 56.4% success [arXiv:2508.11110v1].",
            "sources": ["https://arxiv.org/abs/2508.11110v1"],
        },
    }

    assert experiment.answer_contract_evaluator(output=valid, expected_output=expected).value == 1.0
    valid["payload"]["answer"] = "The result is 56.4%."
    assert experiment.answer_contract_evaluator(output=valid, expected_output=expected).value == 0.0


def test_answer_contract_rejects_extra_and_partial_citation_ids() -> None:
    experiment = _load_module("answer_gate_allowlist", "experiments/agentic_answer_gate.py")
    expected = {
        "http_status": 200,
        "business_status": "success",
        "required_citation_ids": ["2508.11110"],
    }
    output = {
        "http_status": 200,
        "payload": {
            "business_status": "success",
            "answer": "Supported [arXiv:2508.11110v1] but fabricated [arXiv:9999.00001].",
            "sources": ["https://arxiv.org/pdf/2508.11110v1.pdf"],
        },
    }

    assert experiment.answer_contract_evaluator(output=output, expected_output=expected).value == 0.0
    output["payload"]["answer"] = "Prefix only [arXiv:2508.1111]."
    assert experiment.answer_contract_evaluator(output=output, expected_output=expected).value == 0.0


def test_release_script_requires_digest_and_supports_canary_and_rollback(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "deploy/release-image.sh"
    text = script.read_text()

    assert os.access(script, os.X_OK)
    assert "@sha256:" in text
    assert 'canary)' in text
    assert 'promote|rollback)' in text
    assert "/api/v1/ready" in text

    result = subprocess.run(
        [str(script), "promote", __file__, "ghcr.io/example/rag:mutable"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 65
    assert "immutable sha256 digest" in result.stderr

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    old_image = f"ghcr.io/example/rag@sha256:{'a' * 64}"
    candidate = f"ghcr.io/example/rag@sha256:{'b' * 64}"
    deployment_log = tmp_path / "deployments.log"
    fake_docker.write_text(
        """#!/bin/sh
case "$*" in
  *" ps -q api") echo current-api ;;
  "inspect "*" current-api") echo "$FAKE_OLD_IMAGE" ;;
  *" up -d --no-deps --wait "*)
    echo "$RAG_API_IMAGE" >> "$FAKE_DOCKER_LOG"
    [ "$RAG_API_IMAGE" != "$FAKE_CANDIDATE_IMAGE" ] || exit 1
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_OLD_IMAGE": old_image,
        "FAKE_CANDIDATE_IMAGE": candidate,
        "FAKE_DOCKER_LOG": str(deployment_log),
    }
    failed_promotion = subprocess.run(
        [str(script), "promote", __file__, candidate],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert failed_promotion.returncode == 1
    assert deployment_log.read_text(encoding="utf-8").splitlines() == [candidate, old_image]
    assert "restoring previous image" in failed_promotion.stderr
