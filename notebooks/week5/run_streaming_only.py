"""Measure a lightweight Week 5 streaming request."""

import asyncio
import json
import time

import httpx


async def main() -> None:
    request = {
        "query": "What role does diffusion play in code?",
        "top_k": 1,
        "use_hybrid": False,
        "model": "llama3.2:1b",
    }
    started = time.perf_counter()
    first_token_at = None
    token_events = 0
    completed = False
    errors = []
    metadata = {}
    final_answer = ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(360.0)) as client:
        async with client.stream("POST", "http://localhost:8000/api/v1/stream", json=request) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if "sources" in payload:
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

    finished = time.perf_counter()
    ttft = first_token_at - started if first_token_at else None
    print(f"content_type={content_type}")
    print(f"ttft_seconds={ttft:.3f}" if ttft is not None else "ttft_seconds=none")
    print(f"total_seconds={finished - started:.3f}")
    print(f"token_events={token_events} completed={completed} errors={len(errors)}")
    print(
        f"mode={metadata.get('search_mode')} chunks={metadata.get('chunks_used')} "
        f"sources={len(metadata.get('sources', []))} answer_chars={len(final_answer)}"
    )
    print(f"answer_preview={final_answer[:300].replace(chr(10), ' ')}")


if __name__ == "__main__":
    asyncio.run(main())
