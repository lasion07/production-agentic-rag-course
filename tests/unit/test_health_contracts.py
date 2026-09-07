import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Response
from src.config import Settings
from src.main import lifespan
from src.routers.ping import health_check, readiness_check
from starlette.requests import Request


def make_request(*, redis_healthy: bool = True) -> tuple[Request, Settings]:
    settings = Settings(_env_file=None, health_check_timeout_seconds=0.05)
    database = MagicMock()
    database.get_session.return_value.__enter__.return_value = MagicMock()
    database.get_session.return_value.__exit__.return_value = None

    opensearch = MagicMock()
    opensearch.health_check.return_value = True
    opensearch.get_index_stats.return_value = {
        "exists": True,
        "document_count": 81,
    }
    llm = MagicMock(provider_name="test")
    llm.health_check = AsyncMock(
        return_value={"status": "healthy", "message": "reachable"}
    )
    cache = MagicMock()
    cache.health_check = AsyncMock(return_value=redis_healthy)

    app = FastAPI()
    app.state.settings = settings
    app.state.database = database
    app.state.opensearch_client = opensearch
    app.state.llm_client = llm
    app.state.agentic_rag_service = SimpleNamespace(graph=object())
    app.state.cache_client = cache
    app.state.embeddings_service = SimpleNamespace(
        client=SimpleNamespace(is_closed=False)
    )
    app.state.langfuse_tracer = SimpleNamespace(client=None)
    return Request({"type": "http", "app": app}), settings


@pytest.mark.anyio
async def test_readiness_checks_only_required_dependencies():
    request, settings = make_request(redis_healthy=False)
    response = Response()

    result = await readiness_check(request, response, settings)

    assert response.status_code == 200
    assert result.status == "ready"
    assert set(result.services or {}) == {
        "database",
        "opensearch",
        "llm",
        "agentic_rag",
    }
    assert all(service.required for service in (result.services or {}).values())


@pytest.mark.anyio
async def test_readiness_times_out_required_dependency_and_returns_503():
    request, settings = make_request()

    async def slow_health_check():
        await asyncio.sleep(0.2)
        return {"status": "healthy", "message": "late"}

    request.app.state.llm_client.health_check = slow_health_check
    response = Response()
    started = time.perf_counter()

    result = await readiness_check(request, response, settings)

    assert time.perf_counter() - started < 0.15
    assert response.status_code == 503
    assert result.status == "not_ready"
    assert result.services["llm"].status == "unhealthy"
    assert result.services["llm"].message == "Probe timed out"


@pytest.mark.anyio
async def test_optional_redis_failure_degrades_health_but_not_readiness():
    request, settings = make_request(redis_healthy=False)

    result = await health_check(request, settings)

    assert result.status == "degraded"
    assert result.services["redis"].status == "unhealthy"
    assert result.services["redis"].required is False
    assert result.services["database"].status == "healthy"


@pytest.mark.anyio
async def test_redis_is_required_when_rate_limiting_is_enabled():
    request, _settings = make_request(redis_healthy=False)
    settings = Settings(
        _env_file=None,
        health_check_timeout_seconds=0.05,
        api_rate_limit_enabled=True,
    )
    request.app.state.settings = settings
    response = Response()

    result = await readiness_check(request, response, settings)

    assert response.status_code == 503
    assert result.status == "not_ready"
    assert result.services["redis"].required is True
    assert result.services["redis"].status == "unhealthy"


@pytest.mark.anyio
async def test_lifespan_avoids_startup_probes_and_closes_persistent_clients():
    settings = Settings(_env_file=None)
    app = FastAPI()
    database = MagicMock()
    opensearch = MagicMock()
    embeddings = MagicMock()
    embeddings.close = AsyncMock(side_effect=RuntimeError("cleanup failure"))
    llm = MagicMock(provider_name="test", default_model="test-model")
    llm.close = AsyncMock()
    tracer = MagicMock()
    cache = MagicMock()
    cache.close = AsyncMock()
    agentic = SimpleNamespace(graph=object())

    with (
        patch("src.main.get_settings", return_value=settings),
        patch("src.main.make_database", return_value=database) as make_database,
        patch("src.main.make_opensearch_client", return_value=opensearch),
        patch("src.main.make_embeddings_service", return_value=embeddings),
        patch("src.main.make_llm_client", return_value=llm),
        patch("src.main.make_langfuse_tracer", return_value=tracer),
        patch("src.main.make_cache_client", return_value=cache),
        patch("src.main.make_agentic_rag_service", return_value=agentic),
        patch("src.main.make_telegram_service", return_value=None),
    ):
        async with lifespan(app):
            pass

    make_database.assert_called_once_with(validate_connection=False)
    opensearch.health_check.assert_not_called()
    embeddings.close.assert_awaited_once()
    llm.close.assert_awaited_once()
    cache.close.assert_awaited_once()
    opensearch.close.assert_called_once()
    tracer.shutdown.assert_called_once()
    database.teardown.assert_called_once()
