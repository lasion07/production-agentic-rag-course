"""Verify that a digest-pinned deployment serves the expected source commit."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request

IMAGE_PATTERN = re.compile(r"^[^\s]+@sha256:[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def validate_identity(image_ref: str, expected_commit: str) -> None:
    if not IMAGE_PATTERN.fullmatch(image_ref):
        raise ValueError("candidate image must be pinned by sha256 digest")
    if not COMMIT_PATTERN.fullmatch(expected_commit):
        raise ValueError("expected commit must be a full lowercase 40-character SHA")


def verify_deployment(base_url: str, api_key: str, expected_commit: str) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/ready",
        headers={"X-API-Key": api_key},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
        if response.status != 200:
            raise RuntimeError(f"candidate readiness returned HTTP {response.status}")
    if payload.get("status") != "ready":
        raise RuntimeError(f"candidate is not ready: {payload.get('status')}")
    if payload.get("version") != expected_commit:
        raise RuntimeError(
            f"candidate version mismatch: expected={expected_commit} actual={payload.get('version')}"
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    validate_identity(args.image_ref, args.expected_commit)
    if args.base_url:
        api_key = os.environ.get("RAG_API_KEY", "")
        if not api_key:
            raise ValueError("RAG_API_KEY is required to verify a deployed candidate")
        payload = verify_deployment(args.base_url, api_key, args.expected_commit)
        print(json.dumps({"status": payload["status"], "version": payload["version"]}, sort_keys=True))


if __name__ == "__main__":
    main()
