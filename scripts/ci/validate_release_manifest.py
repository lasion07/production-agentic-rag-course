"""Validate immutable evaluation inputs and version metadata used by release gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "evals" / "release_manifest.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_dataset_path(relative_path: str) -> Path:
    path = (PROJECT_ROOT / relative_path).resolve()
    if PROJECT_ROOT not in path.parents:
        raise ValueError(f"Dataset path escapes project root: {relative_path}")
    return path


def _validate_dataset(name: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    path = _resolve_dataset_path(contract["path"])
    payload = path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != contract["sha256"]:
        raise ValueError(
            f"{name} checksum mismatch: expected={contract['sha256']} actual={actual_hash}"
        )

    items = json.loads(payload)
    if not isinstance(items, list) or len(items) != contract["item_count"]:
        raise ValueError(
            f"{name} item count mismatch: expected={contract['item_count']} actual={len(items)}"
        )
    case_ids = [item.get("metadata", {}).get("case_id") for item in items]
    if any(not case_id for case_id in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError(f"{name} requires unique non-empty metadata.case_id values")
    if any("input" not in item or "expectedOutput" not in item for item in items):
        raise ValueError(f"{name} items require input and expectedOutput")
    return items


def validate(*, require_answer_approved: bool = False) -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported release manifest schema_version")

    versions = manifest.get("application_contract", {})
    required_versions = {"model", "prompt_version", "retrieval_version", "response_schema_version"}
    if not required_versions.issubset(versions) or any(
        not isinstance(versions[name], str) or not versions[name].strip()
        for name in required_versions
    ):
        raise ValueError("Release manifest is missing application contract versions")

    datasets = manifest.get("datasets", {})
    fault_contract = datasets["deterministic_faults"]
    answer_contract = datasets["hosted_answers"]
    fault_items = _validate_dataset("deterministic_faults", fault_contract)
    answer_items = _validate_dataset("hosted_answers", answer_contract)

    if fault_contract.get("review_status") != "approved":
        raise ValueError("Deterministic fault dataset must remain human-approved")
    answer_statuses = {
        item.get("metadata", {}).get("review_status") for item in answer_items
    }
    if answer_statuses != {answer_contract.get("review_status")}:
        raise ValueError("Hosted answer item review status differs from release manifest")
    if require_answer_approved and answer_contract.get("review_status") != "approved":
        raise ValueError(
            "Hosted answer dataset is not approved; review all expected outputs before enabling this gate"
        )

    for gate_name, threshold in manifest.get("gates", {}).items():
        if threshold != 1.0:
            raise ValueError(f"P0 release gate {gate_name} must require a 100% pass rate")

    return {
        "manifest_schema": manifest["schema_version"],
        "fault_items": len(fault_items),
        "answer_items": len(answer_items),
        "answer_review_status": answer_contract["review_status"],
        "answer_dataset_name": answer_contract["name"],
        "answer_dataset_version": answer_contract["version"],
        "answer_dataset_timestamp": answer_contract["langfuse_version_timestamp"],
        **versions,
    }


def _write_github_output(path: Path, values: dict[str, Any]) -> None:
    allowed = {
        "answer_dataset_name",
        "answer_dataset_version",
        "answer_dataset_timestamp",
        "model",
        "prompt_version",
        "retrieval_version",
        "response_schema_version",
    }
    lines = []
    for name in sorted(allowed):
        value = str(values[name])
        if "\n" in value or "\r" in value:
            raise ValueError(f"Manifest output {name} must be a single line")
        lines.append(f"{name}={value}\n")
    with path.open("a", encoding="utf-8") as output:
        output.writelines(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-answer-approved", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    result = validate(require_answer_approved=args.require_answer_approved)
    if args.github_output:
        _write_github_output(args.github_output, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
