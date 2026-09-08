"""Langfuse CI experiment for the human-approved hosted answer dataset."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from langfuse import Evaluation, RegressionError, RunnerContext

CITATION_PATTERN = re.compile(r"\[arXiv:([^\]]+)\]", re.IGNORECASE)
ARXIV_SOURCE_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)
VERSION_SUFFIX_PATTERN = re.compile(r"v\d+$", re.IGNORECASE)
PASS_THRESHOLD = 1.0


def _contains(text: str, fragment: str) -> bool:
    return fragment.casefold() in text.casefold()


def _canonical_arxiv_id(value: str) -> str:
    normalized = value.strip().casefold().removesuffix(".pdf")
    return VERSION_SUFFIX_PATTERN.sub("", normalized)


def _source_arxiv_ids(sources: list[str]) -> set[str]:
    return {
        _canonical_arxiv_id(match.group(1))
        for source in sources
        if (match := ARXIV_SOURCE_PATTERN.search(source))
    }


def answer_task(*, item: Any, **_kwargs: Any) -> dict[str, Any]:
    base_url = os.environ["RAG_STAGING_BASE_URL"].rstrip("/")
    api_key = os.environ["RAG_API_KEY"]
    with httpx.Client(base_url=base_url, timeout=180.0) as client:
        response = client.post(
            "/api/v1/ask-agentic",
            headers={"X-API-Key": api_key},
            json=item.input,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {"answer": "", "sources": [], "invalid_json": True}
    return {"http_status": response.status_code, "payload": payload}


def answer_contract_evaluator(
    *, output: dict[str, Any], expected_output: dict[str, Any], **_kwargs: Any
) -> Evaluation:
    payload = output.get("payload", {})
    answer = str(payload.get("answer", ""))
    sources = [str(source) for source in payload.get("sources", [])]
    citation_ids = {_canonical_arxiv_id(match) for match in CITATION_PATTERN.findall(answer)}
    source_ids = _source_arxiv_ids(sources)
    required_citation_ids = {
        _canonical_arxiv_id(value)
        for value in expected_output.get("required_citation_ids", [])
    }
    checks = {
        "http_status": output.get("http_status") == expected_output["http_status"],
        "business_status": payload.get("business_status") == expected_output["business_status"],
        "answer_fragments": all(
            _contains(answer, fragment)
            for fragment in expected_output.get("required_answer_fragments", [])
        ),
        "answer_any_groups": all(
            any(_contains(answer, alternative) for alternative in alternatives)
            for alternatives in expected_output.get("required_answer_any_groups", [])
        ),
        "source_fragments": all(
            any(_contains(source, fragment) for source in sources)
            for fragment in expected_output.get("required_source_fragments", [])
        ),
        "required_citation_ids": required_citation_ids.issubset(citation_ids),
        "citation_allowlist": citation_ids.issubset(source_ids),
    }
    passed = all(checks.values())
    failed_checks = sorted(name for name, value in checks.items() if not value)
    return Evaluation(
        name="answer_contract",
        value=1.0 if passed else 0.0,
        comment="pass" if passed else f"failed checks: {', '.join(failed_checks)}",
    )


def average_answer_contract(*, item_results: list[Any], **_kwargs: Any) -> Evaluation:
    values = [
        evaluation.value
        for result in item_results
        for evaluation in result.evaluations
        if evaluation.name == "answer_contract"
        and isinstance(evaluation.value, (int, float))
    ]
    score = sum(values) / len(values) if values else 0.0
    return Evaluation(name="answer_contract_pass_rate", value=score)


def experiment(context: RunnerContext):
    result = context.run_experiment(
        name="Production Agentic RAG hosted answer gate",
        task=answer_task,
        evaluators=[answer_contract_evaluator],
        run_evaluators=[average_answer_contract],
        max_concurrency=1,
    )
    score = next(
        (
            evaluation.value
            for evaluation in result.run_evaluations
            if evaluation.name == "answer_contract_pass_rate"
        ),
        None,
    )
    if not isinstance(score, (int, float)) or score < PASS_THRESHOLD:
        raise RegressionError(
            result=result,
            metric="answer_contract_pass_rate",
            value=float(score) if isinstance(score, (int, float)) else 0.0,
            threshold=PASS_THRESHOLD,
        )
    return result
