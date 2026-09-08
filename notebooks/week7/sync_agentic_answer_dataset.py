"""Upsert the human-reviewed Week 7 answer-regression dataset into Langfuse."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langfuse import Langfuse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path(__file__).with_name("agentic_answer_eval_dataset_v0.json")
DATASET_NAME = "production-agentic-rag-week7-answer-v0"
ITEM_NAMESPACE = uuid.UUID("248aecbc-ed47-4a08-8760-6e2397b20787")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    if "LANGFUSE_HOST" not in os.environ and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]

    items = json.loads(DATASET_PATH.read_text())
    review_statuses = {
        item.get("metadata", {}).get("review_status") for item in items
    }
    if len(review_statuses) != 1 or None in review_statuses:
        raise ValueError("Dataset items must have one consistent review status")
    review_status = review_statuses.pop()
    client = Langfuse()
    client.create_dataset(
        name=DATASET_NAME,
        description=(
            "Human-reviewed answer-level regression cases for three public arXiv papers. "
            "Review excerpts are metadata-only and must never be passed to the candidate task."
        ),
        metadata={
            "dataset_version": "v0",
            "review_status": review_status,
            "item_count": len(items),
        },
    )

    for item in items:
        case_id = item["metadata"]["case_id"]
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            id=str(uuid.uuid5(ITEM_NAMESPACE, case_id)),
            input=item["input"],
            expected_output=item["expectedOutput"],
            metadata=item["metadata"],
        )

    client.flush()
    print(f"dataset_name={DATASET_NAME}")
    print(f"items_upserted={len(items)}")
    print(f"review_status={review_status}")


if __name__ == "__main__":
    main()
