"""Fast Week 6.1 lab for TTL and versioned cache invalidation."""

import hashlib
import json

import redis

REDIS_URL = "redis://localhost:6379/0"
TTL_SECONDS = 30

REQUEST = {
    "query": "What role does diffusion play in code?",
    "model": "llama3.2:1b",
    "top_k": 1,
    "use_hybrid": False,
    "categories": [],
}


def request_hash(request: dict) -> str:
    canonical = json.dumps(request, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def versioned_key(corpus_version: int) -> str:
    return f"week6_lab:rag:answer:v2:c{corpus_version}:p5:r3:{request_hash(REQUEST)}"


def main() -> None:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    key_c12 = versioned_key(12)
    key_c13 = versioned_key(13)
    simulated_answer = json.dumps({"answer": "Answer generated from corpus version 12"})

    client.delete(key_c12, key_c13)
    client.set(key_c12, simulated_answer, ex=TTL_SECONDS)

    print(f"ping={client.ping()}")
    print(f"c12_exists={bool(client.exists(key_c12))}")
    print(f"c12_ttl_seconds={client.ttl(key_c12)}")
    print(f"same_version_hit={client.get(key_c12) is not None}")
    print(f"c13_key_differs={key_c13 != key_c12}")
    print(f"after_version_bump_hit={client.get(key_c13) is not None}")
    print(f"old_c12_entry_still_exists={bool(client.exists(key_c12))}")

    client.delete(key_c12, key_c13)
    print(f"lab_keys_cleaned={not client.exists(key_c12) and not client.exists(key_c13)}")


if __name__ == "__main__":
    main()
