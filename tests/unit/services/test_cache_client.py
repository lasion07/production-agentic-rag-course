from unittest.mock import MagicMock

import pytest
from src.config import RedisSettings
from src.schemas.api.ask import AskRequest, AskResponse
from src.services.cache.client import CacheClient
from src.services.cache.factory import make_cache_client, make_redis_client


@pytest.mark.asyncio
async def test_lookup_response_reports_hit_miss_and_error():
    redis = MagicMock()
    client = CacheClient(redis, RedisSettings())
    request = AskRequest(query="cache semantics", model="llama3.2:1b")
    response = AskResponse(
        query=request.query,
        answer="cached",
        sources=[],
        chunks_used=0,
        search_mode="bm25",
    )

    redis.get.return_value = response.model_dump_json()
    cached, result = await client.lookup_response(request)
    assert cached == response
    assert result == "hit"

    redis.get.return_value = None
    assert await client.lookup_response(request) == (None, "miss")

    redis.get.side_effect = TimeoutError("redis timeout")
    assert await client.lookup_response(request) == (None, "error")


def test_redis_factory_is_lazy_and_uses_short_non_retrying_timeouts():
    settings = MagicMock()
    settings.redis = RedisSettings(_env_file=None)

    with pytest.MonkeyPatch.context() as monkeypatch:
        constructor = MagicMock()
        monkeypatch.setattr("src.services.cache.factory.redis.Redis", constructor)
        make_redis_client(settings)

    constructor.return_value.ping.assert_not_called()
    options = constructor.call_args.kwargs
    assert options["socket_timeout"] == 1.0
    assert options["socket_connect_timeout"] == 1.0
    assert options["retry_on_timeout"] is False


def test_cache_factory_fails_open_on_local_construction_error():
    settings = MagicMock()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "src.services.cache.factory.make_redis_client",
            MagicMock(side_effect=RuntimeError("redis unavailable")),
        )
        assert make_cache_client(settings) is None
