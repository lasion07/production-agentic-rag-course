from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from src.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Async backend for testing."""
    return "asyncio"


@pytest.fixture
async def client():
    """HTTP client for API testing with mocked services."""
    database = MagicMock()
    database.get_session.return_value.__enter__.return_value = MagicMock()
    database.get_session.return_value.__exit__.return_value = None

    opensearch = MagicMock()
    opensearch.health_check.return_value = True
    opensearch.setup_indices.return_value = {"hybrid_index": True}
    opensearch.client.count.return_value = {"count": 0}

    langfuse = MagicMock()
    telegram = None
    llm = MagicMock(provider_name="test", default_model="test-model")
    llm.health_check = AsyncMock(
        return_value={"status": "healthy", "message": "Test LLM is reachable"}
    )
    agentic_rag = MagicMock()
    agentic_rag.graph = MagicMock()

    with (
        patch("src.main.make_database", return_value=database),
        patch("src.main.make_opensearch_client", return_value=opensearch),
        patch("src.main.make_arxiv_client", return_value=AsyncMock()),
        patch("src.main.make_pdf_parser_service", return_value=AsyncMock()),
        patch("src.main.make_embeddings_service", return_value=AsyncMock()),
        patch("src.main.make_llm_client", return_value=llm),
        patch("src.main.make_langfuse_tracer", return_value=langfuse),
        patch("src.main.make_agentic_rag_service", return_value=agentic_rag),
        patch("src.main.make_cache_client", return_value=MagicMock()),
        patch("src.main.make_telegram_service", return_value=telegram),
        patch("src.repositories.paper.PaperRepository.get_by_arxiv_id") as mock_get_by_id,
    ):
        mock_get_by_id.return_value = None

        async with LifespanManager(app) as manager:
            async with AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client:
                yield client
