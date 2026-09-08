"""Service-backed contracts for the release-gate environment."""

from __future__ import annotations

import os

import pytest
import redis
from opensearchpy import OpenSearch
from sqlalchemy import create_engine, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_SERVICE_INTEGRATION") != "1",
        reason="requires ephemeral PostgreSQL, OpenSearch and Redis services",
    ),
]


def test_postgres_is_at_alembic_head_with_papers_schema() -> None:
    engine = create_engine(os.environ["POSTGRES_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            papers = connection.execute(text("SELECT to_regclass('public.papers')")).scalar_one()
        assert revision == "20260907_0004"
        assert papers == "papers"
    finally:
        engine.dispose()


def test_redis_round_trip() -> None:
    client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_timeout=1, socket_connect_timeout=1)
    key = "ci:release-gate:round-trip"
    try:
        assert client.set(key, "ok", ex=30)
        assert client.get(key) == b"ok"
    finally:
        client.delete(key)
        client.close()


def test_opensearch_aliases_and_embedding_mapping() -> None:
    client = OpenSearch(hosts=[os.environ["OPENSEARCH__HOST"]])
    read_alias = "arxiv-papers-chunks-read"
    write_alias = "arxiv-papers-chunks-write"
    try:
        read_targets = set(client.indices.get_alias(name=read_alias))
        write_targets = set(client.indices.get_alias(name=write_alias))
        assert read_targets == write_targets
        assert len(read_targets) == 1
        target = next(iter(read_targets))
        mapping = client.indices.get_mapping(index=target)[target]["mappings"]
        assert mapping["properties"]["embedding"]["dimension"] == 1024
    finally:
        client.close()
