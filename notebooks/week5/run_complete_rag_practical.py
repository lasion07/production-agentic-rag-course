"""Measure the Week 5 standard and streaming RAG serving paths."""

import asyncio
import json
import re
import time
from typing import Any

import httpx


BASE_URL = "http://localhost:8000/api/v1"
QUERY = 'What does the paper "Diffusion is a code repair operator and generator" claim about code repair?'
REQUEST = {
    "query": QUERY,
    "top_k": 3,
    "use_hybrid": True,
    "model": "llama3.2:1b",
}


def source_ids(urls: list[str]) -> set[str]:
    ids: set[str] = set()
    for url in urls:
        match = re.search(r"/([0-9]+\.[0-9]+)(?:v[0-9]+)?\.pdf", url)
        if match:
            ids.add(match.group(1))
    return ids


def cited_ids(answer: str) -> set[str]:
    return set(re.findall(r"arXiv:([0-9]+\.[0-9]+)(?:v[0-9]+)?", answer, flags=re.IGNORECASE))


async def main() -> None:
    timeout = httpx.Timeout(180.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        health = await client.get(f"{BASE_URL}/health")
        print(f"Health: status={health.status_code}")

        started = time.perf_counter()
        search = await client.post(
            f"{BASE_URL}/hybrid-search/",
            json={"query": QUERY, "size": 5, "use_hybrid": True},
        )
        search_elapsed = time.perf_counter() - started
        search.raise_for_status()
        search_data = search.json()
        search_hits = search_data.get("hits", [])
        search_ids = [hit.get("arxiv_id") for hit in search_hits]
        print(
            f"Search: latency={search_elapsed:.3f}s mode={search_data.get('search_mode')} "
            f"hits={len(search_hits)} unique_papers={len(set(search_ids))} ids={search_ids}"
        )

        started = time.perf_counter()
        standard = await client.post(f"{BASE_URL}/ask", json=REQUEST)
        standard_elapsed = time.perf_counter() - started
        standard.raise_for_status()
        standard_data = standard.json()
        standard_sources = standard_data.get("sources", [])
        standard_answer = standard_data.get("answer", "")
        allowed = source_ids(standard_sources)
        cited = cited_ids(standard_answer)
        print(
            f"Standard: latency={standard_elapsed:.3f}s mode={standard_data.get('search_mode')} "
            f"chunks={standard_data.get('chunks_used')} sources={len(standard_sources)} "
            f"answer_chars={len(standard_answer)}"
        )
        print(
            f"Standard citations: allowed={sorted(allowed)} cited={sorted(cited)} "
            f"invalid={sorted(cited - allowed)}"
        )
        print(f"Standard answer preview: {standard_answer[:300].replace(chr(10), ' ')}")

        stream_started = time.perf_counter()
        first_token_at: float | None = None
        metadata: dict[str, Any] = {}
        final_answer = ""
        errors: list[Any] = []
        token_events = 0
        completed = False

        async with client.stream("POST", f"{BASE_URL}/stream", json=REQUEST) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if "sources" in payload and "chunks_used" in payload:
                    metadata = payload
                if "chunk" in payload:
                    token_events += 1
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                if payload.get("done"):
                    completed = True
                    final_answer = payload.get("answer", "")
                if "error" in payload:
                    errors.append(payload["error"])

        stream_finished = time.perf_counter()
        ttft = first_token_at - stream_started if first_token_at else None
        total = stream_finished - stream_started
        print(
            f"Stream: content_type={content_type!r} ttft={ttft:.3f}s "
            f"total={total:.3f}s token_events={token_events} completed={completed} errors={len(errors)}"
            if ttft is not None
            else f"Stream: content_type={content_type!r} no_token total={total:.3f}s errors={errors}"
        )
        print(
            f"Stream metadata: mode={metadata.get('search_mode')} "
            f"chunks={metadata.get('chunks_used')} sources={len(metadata.get('sources', []))} "
            f"answer_chars={len(final_answer)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
