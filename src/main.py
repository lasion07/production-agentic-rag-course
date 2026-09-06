import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from src.api_errors import register_exception_handlers
from src.config import get_settings
from src.db.factory import make_database
from src.middlewares import RequestContextMiddleware
from src.routers import agentic_ask, hybrid_search, live, ping
from src.routers.ask import ask_router, stream_router
from src.security import enforce_api_access
from src.services.agents.factory import make_agentic_rag_service
from src.services.arxiv.factory import make_arxiv_client
from src.services.cache.factory import make_cache_client
from src.services.embeddings.factory import make_embeddings_service
from src.services.langfuse.factory import make_langfuse_tracer
from src.services.llm.factory import make_llm_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.services.telegram.factory import make_telegram_service

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    """
    logger.info("Starting RAG API...")

    settings = get_settings()
    app.state.settings = settings

    database = make_database()
    app.state.database = database
    logger.info("Database connected")

    # Initialize search service
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client

    # Verify OpenSearch connectivity and create index if needed
    if opensearch_client.health_check():
        logger.info("OpenSearch connected successfully")

        logger.info("OpenSearch schema is managed by an explicit migration job")

        # Get simple statistics
        try:
            stats = opensearch_client.client.count(index=opensearch_client.index_name)
            logger.info(f"OpenSearch ready: {stats['count']} documents indexed")
        except Exception:
            logger.info("OpenSearch index ready (stats unavailable)")
    else:
        logger.warning("OpenSearch connection failed - search features will be limited")

    # Initialize other services (kept for future endpoints and notebook demos)
    app.state.arxiv_client = make_arxiv_client()
    app.state.pdf_parser = make_pdf_parser_service()
    app.state.embeddings_service = make_embeddings_service()
    app.state.llm_client = make_llm_client()
    app.state.langfuse_tracer = make_langfuse_tracer()
    app.state.cache_client = make_cache_client(settings)

    # Construct the same service used by /ask-agentic during startup. A
    # dependency-construction failure must be visible to readiness and must not
    # be rediscovered independently by every user request.
    try:
        app.state.agentic_rag_service = make_agentic_rag_service(
            opensearch_client=app.state.opensearch_client,
            llm_client=app.state.llm_client,
            embeddings_client=app.state.embeddings_service,
            langfuse_tracer=app.state.langfuse_tracer,
            model=settings.selected_llm_model,
        )
        app.state.agentic_rag_error = None
    except Exception as exc:
        app.state.agentic_rag_service = None
        app.state.agentic_rag_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.exception("Agentic RAG service failed readiness construction")
    logger.info(
        "Services initialized: arXiv API client, PDF parser, OpenSearch, Embeddings, "
        "LLM provider=%s model=%s, Langfuse, Cache",
        app.state.llm_client.provider_name,
        app.state.llm_client.default_model,
    )

    # Initialize Telegram bot (Week 7)
    telegram_service = make_telegram_service(
        opensearch_client=app.state.opensearch_client,
        embeddings_client=app.state.embeddings_service,
        llm_client=app.state.llm_client,
        cache_client=app.state.cache_client,
        langfuse_tracer=app.state.langfuse_tracer,
    )

    if telegram_service:
        app.state.telegram_service = telegram_service
        try:
            await telegram_service.start()
            logger.info("Telegram bot started successfully")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
    else:
        logger.info("Telegram bot not configured - skipping initialization")

    logger.info("API ready")
    yield

    # Cleanup
    if hasattr(app.state, "telegram_service") and app.state.telegram_service:
        await app.state.telegram_service.stop()
        logger.info("Telegram bot stopped")

    app.state.langfuse_tracer.shutdown()
    database.teardown()
    logger.info("API shutdown complete")


_bootstrap_settings = get_settings()
_production_docs_disabled = _bootstrap_settings.environment == "production"

app = FastAPI(
    title="arXiv Paper Curator API",
    description="Personal arXiv CS.AI paper curator with RAG capabilities",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
    docs_url=None if _production_docs_disabled else "/docs",
    redoc_url=None if _production_docs_disabled else "/redoc",
    openapi_url=None if _production_docs_disabled else "/openapi.json",
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

# Include routers
app.include_router(live.router, prefix="/api/v1")  # Public process liveness only
app.include_router(
    ping.router,
    prefix="/api/v1",
    dependencies=[Depends(enforce_api_access)],
)  # Detailed dependency health is protected
app.include_router(hybrid_search.router, prefix="/api/v1")  # Search chunks with BM25/hybrid
app.include_router(ask_router, prefix="/api/v1")  # RAG question answering with LLM
app.include_router(stream_router, prefix="/api/v1")  # Streaming RAG responses
app.include_router(agentic_ask.router)  # Agentic RAG with intelligent retrieval


if __name__ == "__main__":
    uvicorn.run(app, port=8000, host="0.0.0.0")
