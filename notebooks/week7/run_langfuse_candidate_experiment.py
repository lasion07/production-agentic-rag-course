"""Publish the deterministic Week 7 candidate contracts as a Langfuse dataset run."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langfuse import Langfuse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, NOTEBOOK_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_agentic_fault_evals import evaluate, probe_case

DATASET_NAME = "production-agentic-rag-week7-regression-v0"
RUN_NAME = "candidate-p1-hardening-2026-09-02"


async def candidate_task(*, item: Any, **_kwargs: Any) -> dict[str, Any]:
    return await probe_case(item.metadata["case_id"], item.input["query"])


def _contract_evaluator(contract_name: str):
    def evaluator(*, output: dict, expected_output: dict, **_kwargs: Any) -> dict[str, Any]:
        status = evaluate(expected_output, output, blocker=None)[contract_name]
        return {
            "name": contract_name,
            "value": 1.0 if status == "pass" else 0.0,
            "comment": f"Deterministic contract result: {status}",
        }

    return evaluator


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    if "LANGFUSE_HOST" not in os.environ and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]

    client = Langfuse()
    dataset = client.get_dataset(DATASET_NAME)
    result = dataset.run_experiment(
        name="Week 7 P1 hardening candidate",
        run_name=RUN_NAME,
        description="Deterministic route, call-budget, and response contracts after P1 hardening.",
        task=candidate_task,
        evaluators=[
            _contract_evaluator("route_contract_pass"),
            _contract_evaluator("call_budget_pass"),
            _contract_evaluator("response_contract_pass"),
        ],
        max_concurrency=1,
        metadata={"candidate": "p1-hardening", "dataset_version": "v0"},
    )
    client.flush()
    print(f"run_name={result.run_name}")
    print(f"items={len(result.item_results)}")
    print(f"dataset_run_url={result.dataset_run_url}")


if __name__ == "__main__":
    main()
