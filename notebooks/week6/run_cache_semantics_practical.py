"""Week 6.1 practical: exact-cache hit, TTL, and versioned namespaces."""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import redis

API_URL = "http://localhost:8000/api/v1/stream"
REDIS_URL = "redis://localhost:6379/0"

REQUEST: dict[str, Any] = {
    "query": "What role does diffusion play in code?",
    "top_k": 1,
    "use_hybrid": False,
    "model": "llama3.2:1b",
}


def current_cache_key(request: dict[str, Any]) -> str:
    """Reproduce CacheClient._generate_cache_key without importing app settings."""
    key_data = {
        "query": request["query"],
        "model": request.get("model", "llama3.2:1b"),
        "top_k": request.get("top_k", 3),
        "use_hybrid": request.get("use_hybrid", True),
        "categories": sorted(request.get("categories") or []),
    }
    canonical = json.dumps(key_data, sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"exact_cache:{digest}"


def versioned_cache_key(request: dict[str, Any], corpus_version: int) -> str:
    """Illustrate a production namespace; it is not implemented by the API yet."""
    digest = current_cache_key(request).removeprefix("exact_cache:")
    return f"rag:answer:v2:c{corpus_version}:p5:r3:{digest}"


@dataclass
class StreamMeasurement:
    ttft: float | None
    total: float
    token_events: int
    completed: bool
    answer: str
    errors: list[str]


async def measure_stream(client: httpx.AsyncClient) -> StreamMeasurement:
    started = time.perf_counter()
    first_token_at = None
    token_events = 0
    completed = False
    answer = ""
    errors: list[str] = []

    async with client.stream("POST", API_URL, json=REQUEST) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if "chunk" in payload:
                token_events += 1
                if first_token_at is None:
                    first_token_at = time.perf_counter()
            if payload.get("done"):
                completed = True
                answer = payload.get("answer", "")
            if "error" in payload:
                errors.append(payload["error"])

    finished = time.perf_counter()
    return StreamMeasurement(
        ttft=first_token_at - started if first_token_at else None,
        total=finished - started,
        token_events=token_events,
        completed=completed,
        answer=answer,
        errors=errors,
    )


def show_measurement(label: str, result: StreamMeasurement) -> None:
    ttft = f"{result.ttft:.3f}s" if result.ttft is not None else "none"
    print(
        f"{label}: ttft={ttft} total={result.total:.3f}s "
        f"events={result.token_events} completed={result.completed} "
        f"errors={len(result.errors)} answer_chars={len(result.answer)}"
    )


async def main() -> None:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    cache_key = current_cache_key(REQUEST)

    print(f"current_key={cache_key}")
    deleted = redis_client.delete(cache_key)
    print(f"reset_target_key={bool(deleted)}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0)) as client:
        first = await measure_stream(client)
        ttl_after_first = redis_client.ttl(cache_key)
        second = await measure_stream(client)

    show_measurement("first_request_expected_miss", first)
    print(f"ttl_after_first_seconds={ttl_after_first}")
    show_measurement("second_request_expected_hit", second)
    print(f"answers_identical={first.answer == second.answer}")

    key_c12 = versioned_cache_key(REQUEST, corpus_version=12)
    key_c13 = versioned_cache_key(REQUEST, corpus_version=13)
    print(f"versioned_key_before={key_c12}")
    print(f"versioned_key_after={key_c13}")
    print(f"logical_invalidation={key_c12 != key_c13}")


if __name__ == "__main__":
    asyncio.run(main())
