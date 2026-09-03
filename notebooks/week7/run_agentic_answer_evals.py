"""Run non-hermetic answer contracts against a live Agentic RAG endpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

DATASET_PATH = Path(__file__).with_name("agentic_answer_eval_dataset_v0.json")


def evaluate_item(item: dict[str, Any], response: httpx.Response) -> dict[str, Any]:
    expected = item["expectedOutput"]
    payload = response.json()
    answer = payload.get("answer", "")
    sources = payload.get("sources", [])
    checks = {
        "http_status": response.status_code == expected["http_status"],
        "business_status": payload.get("business_status") == expected["business_status"],
        "answer_fragments": all(fragment in answer for fragment in expected["required_answer_fragments"]),
        "source_fragments": all(
            any(fragment in source for source in sources) for fragment in expected["required_source_fragments"]
        ),
    }
    return {
        "case_id": item["metadata"]["case_id"],
        "passed": all(checks.values()),
        "checks": checks,
        "trace_id": payload.get("trace_id"),
        "answer": answer,
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
