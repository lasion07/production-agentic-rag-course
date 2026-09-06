"""Run non-hermetic answer contracts against a live Agentic RAG endpoint."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import httpx

DATASET_PATH = Path(__file__).with_name("agentic_answer_eval_dataset_v0.json")
CITATION_PATTERN = re.compile(r"\[arXiv:([^\]]+)\]", re.IGNORECASE)


def _contains(text: str, fragment: str) -> bool:
    return fragment.casefold() in text.casefold()


def _citation_ids(answer: str) -> set[str]:
    return {match.casefold() for match in CITATION_PATTERN.findall(answer)}


def _citation_matches(actual_ids: set[str], required_fragment: str) -> bool:
    required = required_fragment.casefold()
    return any(required in actual for actual in actual_ids)


def evaluate_item(item: dict[str, Any], response: httpx.Response) -> dict[str, Any]:
    expected = item["expectedOutput"]
    payload = response.json()
    answer = payload.get("answer", "")
    sources = payload.get("sources", [])
    citation_ids = _citation_ids(answer)
    required_answer_fragments = expected.get("required_answer_fragments", [])
    required_answer_any_groups = expected.get("required_answer_any_groups", [])
    required_source_fragments = expected.get("required_source_fragments", [])
    required_citation_ids = expected.get("required_citation_ids", [])
    checks = {
        "http_status": response.status_code == expected["http_status"],
        "business_status": payload.get("business_status") == expected["business_status"],
        "answer_fragments": all(_contains(answer, fragment) for fragment in required_answer_fragments),
        "answer_any_groups": all(
            any(_contains(answer, alternative) for alternative in alternatives)
            for alternatives in required_answer_any_groups
        ),
        "source_fragments": all(
            any(_contains(source, fragment) for source in sources) for fragment in required_source_fragments
        ),
        "citation_ids": all(
            _citation_matches(citation_ids, required_id) for required_id in required_citation_ids
        ),
    }
    return {
        "case_id": item["metadata"]["case_id"],
        "passed": all(checks.values()),
        "checks": checks,
        "trace_id": payload.get("trace_id"),
        "answer_preview": answer[:500],
        "citation_ids": sorted(citation_ids),
        "sources": sources,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text())
    failures = 0
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        for item in dataset:
            response = client.post("/api/v1/ask-agentic", json=item["input"])
            result = evaluate_item(item, response)
            failures += int(not result["passed"])
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    print(f"summary=passed:{len(dataset) - failures} failed:{failures}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
