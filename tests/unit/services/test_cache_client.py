from unittest.mock import MagicMock

import pytest
from src.config import RedisSettings
from src.schemas.api.ask import AskRequest, AskResponse
from src.services.cache.client import CacheClient


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
