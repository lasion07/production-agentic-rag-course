"""Bounded readiness and protected dependency-health probes."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from ..api_errors import PUBLIC_ERROR_RESPONSES
from ..dependencies import SettingsDep
from ..schemas.api.health import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)
router = APIRouter(responses=PUBLIC_ERROR_RESPONSES)

Probe = Callable[[], Awaitable[tuple[str, str]]]


async def _bounded_probe(
    name: str,
    probe: Probe,
    *,
    required: bool,
    timeout: float,
) -> tuple[str, ServiceStatus]:
    """Run one dependency probe under a hard response-time budget."""
    started = time.perf_counter()
    try:
        probe_status, message = await asyncio.wait_for(probe(), timeout=timeout)
    except TimeoutError:
        probe_status, message = "unhealthy", "Probe timed out"
        logger.warning("Dependency probe timed out: %s", name)
    except Exception:
        probe_status, message = "unhealthy", "Dependency unavailable"
        logger.warning("Dependency probe failed: %s", name, exc_info=True)

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return name, ServiceStatus(
        status=probe_status,
        message=message,
        required=required,
        latency_ms=latency_ms,
    )


async def _collect_dependency_health(
    request: Request,
    *,
    timeout: float,
    include_optional: bool,
) -> dict[str, ServiceStatus]:
    """Probe required serving dependencies concurrently, plus optional services on demand."""
    state = request.app.state

    async def database_probe() -> tuple[str, str]:
        def check() -> None:
            with state.database.get_session() as session:
                session.execute(text("SELECT 1"))

        await asyncio.to_thread(check)
        return "healthy", "Query succeeded"

    async def opensearch_probe() -> tuple[str, str]:
        healthy = await asyncio.to_thread(state.opensearch_client.health_check)
        if not healthy:
            raise RuntimeError("OpenSearch health check failed")
        stats = await asyncio.to_thread(state.opensearch_client.get_index_stats)
        if not stats.get("exists") or stats.get("error"):
            raise RuntimeError("Serving index alias is unavailable")
        return (
            "healthy",
            f"Read alias available with {stats.get('document_count', 0)} documents",
        )

    async def llm_probe() -> tuple[str, str]:
        result = await state.llm_client.health_check()
        if result.get("status") != "healthy":
            raise RuntimeError("LLM health check failed")
        return "healthy", f"{state.llm_client.provider_name} API reachable"

    async def agentic_probe() -> tuple[str, str]:
        service = getattr(state, "agentic_rag_service", None)
        if service is None or getattr(service, "graph", None) is None:
            raise RuntimeError("Agentic RAG graph is unavailable")
        return "healthy", "Service constructed and graph compiled"

    async def redis_probe() -> tuple[str, str]:
        cache = getattr(state, "cache_client", None)
        if cache is None or not await cache.health_check():
            raise RuntimeError("Redis is unavailable")
        role = "security and cache" if state.settings.api_rate_limit_enabled else "optional cache"
        return "healthy", f"{role.capitalize()} reachable"

    specs: list[tuple[str, Probe, bool]] = [
        ("database", database_probe, True),
        ("opensearch", opensearch_probe, True),
        ("llm", llm_probe, True),
        ("agentic_rag", agentic_probe, True),
    ]
    if state.settings.api_rate_limit_enabled:
        specs.append(("redis", redis_probe, True))

    if include_optional:
        async def embeddings_probe() -> tuple[str, str]:
            embeddings = getattr(state, "embeddings_service", None)
            if embeddings is None or getattr(embeddings.client, "is_closed", False) is True:
                raise RuntimeError("Embeddings client is unavailable")
            return "healthy", "Client constructed; remote API not probed"

        async def langfuse_probe() -> tuple[str, str]:
            tracer = getattr(state, "langfuse_tracer", None)
            if not state.settings.langfuse.enabled:
                return "disabled", "Tracing disabled by configuration"
            if tracer is None or tracer.client is None:
                raise RuntimeError("Langfuse client is unavailable")
            return "healthy", "Telemetry exporter configured"

        if not state.settings.api_rate_limit_enabled:
            specs.append(("redis", redis_probe, False))
        specs.extend(
            [
                ("embeddings", embeddings_probe, False),
                ("langfuse", langfuse_probe, False),
            ]
        )

    results = await asyncio.gather(
        *(
            _bounded_probe(name, probe, required=required, timeout=timeout)
            for name, probe, required in specs
        )
    )
    return dict(results)


def _response(
    *,
    status_value: str,
    settings: SettingsDep,
    services: dict[str, ServiceStatus],
) -> HealthResponse:
    return HealthResponse(
        status=status_value,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )


@router.get("/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check(
    request: Request,
    response: Response,
    settings: SettingsDep,
) -> HealthResponse:
    """Return 503 unless every required serving dependency is healthy."""
    services = await _collect_dependency_health(
        request,
        timeout=settings.health_check_timeout_seconds,
        include_optional=False,
    )
    ready = all(service.status == "healthy" for service in services.values())
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return _response(
        status_value="ready" if ready else "not_ready",
        settings=settings,
        services=services,
    )


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(request: Request, settings: SettingsDep) -> HealthResponse:
    """Return protected, detailed dependency status without changing HTTP status."""
    services = await _collect_dependency_health(
        request,
        timeout=settings.health_check_timeout_seconds,
        include_optional=True,
    )
    required_failed = any(
        service.required and service.status != "healthy" for service in services.values()
    )
    optional_failed = any(
        not service.required and service.status == "unhealthy" for service in services.values()
    )
    overall = "unhealthy" if required_failed else "degraded" if optional_failed else "ok"
    return _response(status_value=overall, settings=settings, services=services)
