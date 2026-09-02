"""Fetch and audit the newest real API trace from Langfuse Cloud."""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.services.langfuse.client import LangfuseTracer


def main() -> None:
    tracer = LangfuseTracer(get_settings())
    if tracer.client is None:
        raise RuntimeError("Langfuse is disabled or credentials are missing")

    trace = None
    for attempt in range(6):
        traces = tracer.client.api.trace.list(limit=10, name="rag-request", user_id="api_user")
        if traces.data:
            trace = tracer.client.api.trace.get(traces.data[0].id)
            break
        if attempt == 5:
            raise RuntimeError("No rag-request trace from api_user was found")
        time.sleep(2 + attempt)

    observations = getattr(trace, "observations", [])
    summary = sorted(
        (str(getattr(item, "name", "unknown")), str(getattr(item, "type", "unknown")))
        for item in observations
    )
    names = {name for name, _observation_type in summary}
    assert {"rag-request", "cache-lookup", "search-retrieval", "prompt-construction", "llm-generation"} <= names

    serialized = str(trace.model_dump())
    assert "What role do diffusion models play in last-mile code repair?" not in serialized
    assert "Diffusion models have emerged as a powerful paradigm" not in serialized

    generation = next(item for item in observations if getattr(item, "name", None) == "llm-generation")
    print(f"trace_id={trace.id}")
    print(f"trace_url={tracer.get_trace_url(trace.id)}")
    print(f"latency_seconds={getattr(trace, 'latency', None)}")
    print(f"observations={len(observations)}")
    print(f"observation_summary={summary}")
    print(f"generation_usage={getattr(generation, 'usage_details', None)}")
    print("privacy_audit=passed")
    tracer.shutdown()


if __name__ == "__main__":
    main()
