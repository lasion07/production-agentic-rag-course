from fastapi import APIRouter, Request
from sqlalchemy import text

from ..api_errors import PUBLIC_ERROR_RESPONSES
from ..dependencies import DatabaseDep, LLMDep, OpenSearchDep, SettingsDep
from ..schemas.api.health import HealthResponse, ServiceStatus

router = APIRouter(responses=PUBLIC_ERROR_RESPONSES)


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(
    request: Request,
    settings: SettingsDep,
    database: DatabaseDep,
    opensearch_client: OpenSearchDep,
    llm_client: LLMDep,
) -> HealthResponse:
    """Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"

    def _check_service(name: str, check_func, *args, **kwargs):
        """Helper to standardize service health checks."""
        try:
            if kwargs.get("is_async"):
                # Handle async functions separately in the calling code
                return check_func(*args)
            result = check_func(*args)
            services[name] = result
            if result.status != "healthy":
                nonlocal overall_status
                overall_status = "degraded"
        except Exception as e:
            services[name] = ServiceStatus(status="unhealthy", message=str(e))
            overall_status = "degraded"

    # Database check
    def _check_database():
        with database.get_session() as session:
            session.execute(text("SELECT 1"))
        return ServiceStatus(status="healthy", message="Connected successfully")

    # OpenSearch check
    def _check_opensearch():
        if not opensearch_client.health_check():
            return ServiceStatus(status="unhealthy", message="Not responding")
        stats = opensearch_client.get_index_stats()
        return ServiceStatus(
            status="healthy",
            message=f"Index '{stats.get('index_name', 'unknown')}' with {stats.get('document_count', 0)} documents",
        )

    # Run synchronous checks
    _check_service("database", _check_database)
    _check_service("opensearch", _check_opensearch)

    # Handle the active LLM provider async check separately.
    try:
        llm_health = await llm_client.health_check()
        services["llm"] = ServiceStatus(
            status=llm_health["status"],
            message=f"{llm_client.provider_name}: {llm_health['message']}",
        )
        if llm_health["status"] != "healthy":
            overall_status = "degraded"
    except Exception as e:
        services["llm"] = ServiceStatus(status="unhealthy", message=f"{llm_client.provider_name}: {e}")
        overall_status = "degraded"

    agentic_service = getattr(request.app.state, "agentic_rag_service", None)
    if agentic_service is not None and getattr(agentic_service, "graph", None) is not None:
        services["agentic_rag"] = ServiceStatus(
            status="healthy",
            message="Service constructed and graph compiled",
        )
    else:
        services["agentic_rag"] = ServiceStatus(
            status="unhealthy",
            message=getattr(request.app.state, "agentic_rag_error", "Service not constructed"),
        )
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
