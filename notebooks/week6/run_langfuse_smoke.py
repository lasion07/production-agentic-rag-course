"""Emit and verify a privacy-safe Langfuse trace without calling external LLMs."""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_settings
from src.services.langfuse.client import LangfuseTracer
from src.services.langfuse.tracer import RAGTracer


def main() -> None:
    tracer = LangfuseTracer(get_settings())
    if tracer.client is None:
        raise RuntimeError("Langfuse is disabled or credentials are missing")

    rag = RAGTracer(tracer)
    trace_id = None
    with rag.trace_request("week6_student", "privacy-safe Langfuse smoke test") as root:
        trace_id = tracer.get_trace_id()

        with rag.trace_cache("lookup") as cache_span:
            rag.end_cache(cache_span, "miss")

        with rag.trace_search(root, "privacy-safe Langfuse smoke test", 3) as search_span:
            rag.end_search(search_span, [{"arxiv_id": "demo"}], ["demo"], 1)

        with rag.trace_generation(root, "smoke-model", "synthetic prompt") as generation:
            rag.end_generation(
                generation,
                "synthetic grounded answer",
                "smoke-model",
                usage_metadata={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                finish_reason="stop",
            )

        rag.end_request(root, "synthetic grounded answer", 0.01)

    if not trace_id:
        raise RuntimeError("Langfuse did not create a trace id")

    # Short-lived scripts must flush explicitly; the long-running API flushes in
    # the background and calls shutdown during application shutdown.
    tracer.flush()

    fetched = None
    for attempt in range(5):
        try:
            fetched = tracer.client.api.trace.get(trace_id)
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(1 + attempt)

    observations = getattr(fetched, "observations", [])
    observation_summary = sorted(
        (str(getattr(item, "name", "unknown")), str(getattr(item, "type", "unknown")))
        for item in observations
    )
    serialized_trace = str(fetched.model_dump())
    expected_names = {"rag-request", "cache-lookup", "search-retrieval", "llm-generation"}
    actual_names = {name for name, _observation_type in observation_summary}
    assert actual_names == expected_names
    assert getattr(fetched, "user_id", None) == "week6_student"
    assert getattr(fetched, "session_id", None) == "session-week6_student"
    assert "privacy-safe Langfuse smoke test" not in serialized_trace
    assert "synthetic grounded answer" not in serialized_trace
    assert "synthetic prompt" not in serialized_trace

    print(f"trace_id={trace_id}")
    print(f"trace_url={tracer.get_trace_url(trace_id)}")
    print(f"trace_name={getattr(fetched, 'name', None)}")
    print(f"trace_user_id={getattr(fetched, 'user_id', None)}")
    print(f"trace_session_id={getattr(fetched, 'session_id', None)}")
    print(f"observations={len(observations)}")
    print(f"observation_summary={observation_summary}")
    print("privacy_audit=passed")
    print(f"capture_content={tracer.settings.capture_content}")
    tracer.shutdown()


if __name__ == "__main__":
    main()
