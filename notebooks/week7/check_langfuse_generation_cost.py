"""Check the Langfuse p95 generation cost against warning/alert budgets."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--warning-usd", type=float, default=0.005)
    parser.add_argument("--alert-usd", type=float, default=0.010)
    parser.add_argument("--environment", default="development")
    parser.add_argument("--observation-name", default="ChatOpenAI")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    if not 0 <= args.warning_usd < args.alert_usd:
        raise SystemExit("Expected 0 <= warning-usd < alert-usd")

    load_dotenv(PROJECT_ROOT / ".env")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
    model = args.model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    if not all((public_key, secret_key, base_url, model)):
        raise SystemExit(
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL/HOST, "
            "and LLM_MODEL/OPENAI_MODEL (or --model) are required"
        )

    to_timestamp = datetime.now(UTC)
    from_timestamp = to_timestamp - timedelta(hours=args.hours)
    query = {
        "view": "observations",
        "metrics": [{"measure": "totalCost", "aggregation": "p95"}],
        "dimensions": [],
        "filters": [
            {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"},
            {
                "column": "name",
                "operator": "=",
                "value": args.observation_name,
                "type": "string",
            },
            {
                "column": "environment",
                "operator": "=",
                "value": args.environment,
                "type": "string",
            },
            {
                "column": "providedModelName",
                "operator": "=",
                "value": model,
                "type": "string",
            },
        ],
        "fromTimestamp": from_timestamp.isoformat().replace("+00:00", "Z"),
        "toTimestamp": to_timestamp.isoformat().replace("+00:00", "Z"),
    }
    response = httpx.get(
        f"{base_url.rstrip('/')}/api/public/v2/metrics",
        params={"query": json.dumps(query)},
        auth=(public_key, secret_key),
        timeout=20.0,
    )
    response.raise_for_status()
    rows = response.json().get("data", [])
    p95_cost = rows[0].get("p95_totalCost") if rows else None
    if p95_cost is None:
        result = "no_data"
        exit_code = 0
    elif p95_cost >= args.alert_usd:
        result = "alert"
        exit_code = 3
    elif p95_cost >= args.warning_usd:
        result = "warning"
        exit_code = 2
    else:
        result = "ok"
        exit_code = 0

    print(
        json.dumps(
            {
                "result": result,
                "p95_generation_cost_usd": p95_cost,
                "warning_threshold_usd": args.warning_usd,
                "alert_threshold_usd": args.alert_usd,
                "window_hours": args.hours,
                "environment": args.environment,
                "observation_name": args.observation_name,
                "model": model,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
