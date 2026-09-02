"""Week 6.2 lab: cache stampede, single-flight, fail-open, and metrics."""

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field

import redis.asyncio as redis

REQUESTS = 100
WORKERS = 4
GENERATION_SECONDS = 0.2
REDIS_URL = "redis://localhost:6379/0"
LAB_CACHE_KEY = "week6_lab:stampede:answer"
LAB_LOCK_KEY = "week6_lab:stampede:lock"


@dataclass
class Metrics:
    cache_hits: int = 0
    cache_misses: int = 0
    cache_errors: int = 0
    generations: int = 0
    lock_contentions: int = 0
    coalesced_requests: int = 0
    lock_wait_seconds: list[float] = field(default_factory=list)


async def generate_answer(metrics: Metrics) -> str:
    metrics.generations += 1
    await asyncio.sleep(GENERATION_SECONDS)
    return "simulated grounded answer"


async def simulate_without_lock() -> tuple[Metrics, float]:
    cache: dict[str, str] = {}
    metrics = Metrics()

    async def request() -> str:
        cached = cache.get("answer")
        if cached is not None:
            metrics.cache_hits += 1
            return cached
        metrics.cache_misses += 1
        answer = await generate_answer(metrics)
        cache["answer"] = answer
        return answer

    started = time.perf_counter()
    await asyncio.gather(*(request() for _ in range(REQUESTS)))
    return metrics, time.perf_counter() - started


async def simulate_local_locks() -> tuple[Metrics, float]:
    cache: dict[str, str] = {}
    locks = [asyncio.Lock() for _ in range(WORKERS)]
    metrics = Metrics()

    async def request(worker_id: int) -> str:
        cached = cache.get("answer")
        if cached is not None:
            metrics.cache_hits += 1
            return cached
        metrics.cache_misses += 1

        async with locks[worker_id]:
            cached = cache.get("answer")
            if cached is not None:
                metrics.coalesced_requests += 1
                return cached
            answer = await generate_answer(metrics)
            cache["answer"] = answer
            return answer

    started = time.perf_counter()
    await asyncio.gather(*(request(index % WORKERS) for index in range(REQUESTS)))
    return metrics, time.perf_counter() - started


async def release_owned_lock(client: redis.Redis, token: str) -> None:
    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    await client.eval(script, 1, LAB_LOCK_KEY, token)


async def simulate_distributed_lock(client: redis.Redis) -> tuple[Metrics, float]:
    await client.delete(LAB_CACHE_KEY, LAB_LOCK_KEY)
    metrics = Metrics()

    async def request() -> str:
        cached = await client.get(LAB_CACHE_KEY)
        if cached is not None:
            metrics.cache_hits += 1
            return cached

        metrics.cache_misses += 1
        token = str(uuid.uuid4())
        wait_started = time.perf_counter()
        recorded_contention = False
        deadline = wait_started + 3.0

        while time.perf_counter() < deadline:
            acquired = await client.set(LAB_LOCK_KEY, token, nx=True, px=2_000)
            if acquired:
                try:
                    cached = await client.get(LAB_CACHE_KEY)
                    if cached is not None:
                        metrics.coalesced_requests += 1
                        return cached
                    answer = await generate_answer(metrics)
                    await client.set(LAB_CACHE_KEY, answer, ex=30)
                    return answer
                finally:
                    await release_owned_lock(client, token)

            if not recorded_contention:
                metrics.lock_contentions += 1
                recorded_contention = True

            await asyncio.sleep(random.uniform(0.005, 0.015))
            cached = await client.get(LAB_CACHE_KEY)
            if cached is not None:
                metrics.coalesced_requests += 1
                metrics.lock_wait_seconds.append(time.perf_counter() - wait_started)
                return cached

        raise TimeoutError("single-flight wait budget exhausted")

    started = time.perf_counter()
    await asyncio.gather(*(request() for _ in range(REQUESTS)))
    duration = time.perf_counter() - started
    await client.delete(LAB_CACHE_KEY, LAB_LOCK_KEY)
    return metrics, duration


async def simulate_fail_open() -> tuple[Metrics, int, float]:
    metrics = Metrics()

    async def request() -> str:
        try:
            raise ConnectionError("simulated Redis outage")
        except ConnectionError:
            metrics.cache_errors += 1
        return await generate_answer(metrics)

    started = time.perf_counter()
    responses = await asyncio.gather(*(request() for _ in range(10)))
    return metrics, len(responses), time.perf_counter() - started


def print_metrics(name: str, metrics: Metrics, duration: float) -> None:
    waits = sorted(metrics.lock_wait_seconds)
    p95_wait = waits[int(0.95 * (len(waits) - 1))] if waits else 0.0
    print(
        f"{name}: requests={REQUESTS} generations={metrics.generations} "
        f"hits={metrics.cache_hits} misses={metrics.cache_misses} "
        f"contentions={metrics.lock_contentions} coalesced={metrics.coalesced_requests} "
        f"p95_lock_wait={p95_wait:.3f}s total={duration:.3f}s"
    )


async def main() -> None:
    no_lock, no_lock_duration = await simulate_without_lock()
    local_lock, local_lock_duration = await simulate_local_locks()

    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        distributed, distributed_duration = await simulate_distributed_lock(client)
    finally:
        await client.aclose()

    fail_open, successful_responses, fail_open_duration = await simulate_fail_open()

    print_metrics("no_lock", no_lock, no_lock_duration)
    print_metrics("four_local_locks", local_lock, local_lock_duration)
    print_metrics("redis_distributed_lock", distributed, distributed_duration)
    print(
        f"fail_open: requests=10 redis_errors={fail_open.cache_errors} "
        f"successful_responses={successful_responses} generations={fail_open.generations} "
        f"total={fail_open_duration:.3f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
