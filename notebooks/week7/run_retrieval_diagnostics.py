"""Locate each approved gold chunk in candidate generation and final selection."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.config import Settings
from src.services.agents.tools import execute_retrieval
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

DATASET_PATH = Path(__file__).with_name("agentic_answer_eval_dataset_v0.json")


async def run(opensearch_host: str, candidate_multiplier: int) -> int:
    settings = Settings()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    search = OpenSearchClient(opensearch_host, settings)
    embeddings = JinaEmbeddingsClient(settings.jina_api_key)
    failures = 0
    try:
        for item in dataset:
            outcome = await execute_retrieval(
                query=item["input"]["query"],
                opensearch_client=search,
                embeddings_client=embeddings,
                top_k=item["input"]["top_k"],
                use_hybrid=item["input"]["use_hybrid"],
                candidate_multiplier=candidate_multiplier,
            )
            candidate_rows = outcome.diagnostics.get("candidate_chunks", [])
            candidate_ids = {
                row["chunk_id"]
                for row in candidate_rows
            }
            selected_ids = set(outcome.diagnostics.get("selected_chunk_ids", []))
            gold_ids = {
                evidence["chunk_id"] for evidence in item["metadata"]["gold_evidence"]
            }
            locations = {
                chunk_id: (
                    "final_context"
                    if chunk_id in selected_ids
                    else "context_selection"
                    if chunk_id in candidate_ids
                    else "candidate_generation"
                )
                for chunk_id in sorted(gold_ids)
            }
            gold_details = {
                chunk_id: next(
                    (row for row in candidate_rows if row["chunk_id"] == chunk_id),
                    None,
                )
                for chunk_id in sorted(gold_ids)
            }
            passed = all(location == "final_context" for location in locations.values())
            failures += int(not passed)
            print(
                json.dumps(
                    {
                        "case_id": item["metadata"]["case_id"],
                        "status": outcome.status,
                        "search_mode": outcome.actual_search_mode,
                        "candidate_count": outcome.diagnostics.get("candidate_count", 0),
                        "selected_count": outcome.diagnostics.get("selected_count", 0),
                        "selected_chunk_ids": outcome.diagnostics.get(
                            "selected_chunk_ids", []
                        ),
                        "gold_locations": locations,
                        "gold_details": gold_details,
                        "passed": passed,
                    },
                    sort_keys=True,
                )
            )
    finally:
        await embeddings.close()
        search.close()

    print(f"summary=passed:{len(dataset) - failures} failed:{failures}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opensearch-host", default="http://localhost:9200")
    parser.add_argument("--candidate-multiplier", type=int, default=4)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.opensearch_host, args.candidate_multiplier)))


if __name__ == "__main__":
    main()
