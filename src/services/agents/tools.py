import asyncio
import logging
import time
from typing import List, Optional

import httpx
from langchain_core.documents import Document
from langchain_core.tools import tool
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

from .models import RetrievalOutcome

logger = logging.getLogger(__name__)


class RetrievalUnavailableError(RuntimeError):
    """Raised when the search dependency cannot execute a retrieval."""


def _has_time(
    deadline_monotonic: Optional[float],
    generation_reserve_seconds: float,
) -> bool:
    if deadline_monotonic is None:
        return True
    return time.monotonic() < deadline_monotonic - generation_reserve_seconds


def _attempt_timeout(
    configured_timeout: float,
    deadline_monotonic: Optional[float],
    generation_reserve_seconds: float,
) -> float:
    if deadline_monotonic is None:
        return configured_timeout
    available = deadline_monotonic - generation_reserve_seconds - time.monotonic()
    return max(0.001, min(configured_timeout, available))


def _retry_delay_seconds(exc: Exception, attempt_index: int) -> float:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return min(0.25 * (2**attempt_index), 2.0)


def _embedding_error_is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


def _documents_from_hits(hits: list[dict], search_mode: str, top_k: int) -> List[Document]:
    documents: List[Document] = []
    for hit in hits:
        documents.append(
            Document(
                page_content=hit["chunk_text"],
                metadata={
                    "arxiv_id": hit["arxiv_id"],
                    "title": hit.get("title", ""),
                    "authors": hit.get("authors", ""),
                    "score": hit.get("score", 0.0),
                    "source": f"https://arxiv.org/pdf/{hit['arxiv_id']}.pdf",
                    "section": hit.get("section_name", ""),
                    "search_mode": search_mode,
                    "top_k": top_k,
                },
            )
        )
    return documents


async def execute_retrieval(
    *,
    query: str,
    opensearch_client: OpenSearchClient,
    embeddings_client: JinaEmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True,
    categories: Optional[List[str]] = None,
    max_embedding_attempts: int = 2,
    max_search_attempts: int = 2,
    embedding_attempt_timeout_seconds: float = 10.0,
    search_attempt_timeout_seconds: float = 5.0,
    deadline_monotonic: Optional[float] = None,
    generation_reserve_seconds: float = 5.0,
) -> RetrievalOutcome:
    """Execute bounded retrieval without masking dependency failures.

    Embedding failures may degrade hybrid retrieval to BM25. Search failures are
    retried with the same operation and ultimately become an explicit error; they
    are never represented as a successful empty result.
    """

    requested_mode = "hybrid" if use_hybrid else "bm25"
    actual_mode = requested_mode
    embedding: Optional[list[float]] = None
    embedding_attempts = 0
    fallbacks = 0

    if use_hybrid:
        last_embedding_error: Optional[Exception] = None
        for attempt in range(max_embedding_attempts):
            if not _has_time(deadline_monotonic, generation_reserve_seconds):
                break
            embedding_attempts += 1
            try:
                embedding = await asyncio.wait_for(
                    embeddings_client.embed_query(query),
                    timeout=_attempt_timeout(
                        embedding_attempt_timeout_seconds,
                        deadline_monotonic,
                        generation_reserve_seconds,
                    ),
                )
                last_embedding_error = None
                break
            except Exception as exc:
                last_embedding_error = exc
                retryable = _embedding_error_is_retryable(exc)
                logger.warning(
                    "Embedding attempt %s/%s failed: %s",
                    embedding_attempts,
                    max_embedding_attempts,
                    type(exc).__name__,
                )
                if not retryable:
                    break
                if attempt + 1 < max_embedding_attempts:
                    delay = _retry_delay_seconds(exc, attempt)
                    if deadline_monotonic is not None and not _has_time(deadline_monotonic - delay, generation_reserve_seconds):
                        break
                    await asyncio.sleep(delay)

        if embedding is None:
            actual_mode = "bm25"
            fallbacks = 1
            logger.warning(
                "Falling back to BM25 after embedding failure: %s",
                type(last_embedding_error).__name__ if last_embedding_error else "deadline_budget",
            )

    search_failures = 0
    last_search_error: Optional[Exception] = None
    for search_attempt in range(1, max_search_attempts + 1):
        if not _has_time(deadline_monotonic, generation_reserve_seconds):
            last_search_error = TimeoutError("retrieval deadline budget exhausted")
            break
        try:
            search_results = await asyncio.wait_for(
                asyncio.to_thread(
                    opensearch_client.search_unified,
                    query=query,
                    query_embedding=embedding,
                    size=top_k,
                    categories=categories,
                    use_hybrid=actual_mode == "hybrid",
                ),
                timeout=_attempt_timeout(
                    search_attempt_timeout_seconds,
                    deadline_monotonic,
                    generation_reserve_seconds,
                ),
            )
            documents = _documents_from_hits(search_results.get("hits", []), actual_mode, top_k)
            return RetrievalOutcome(
                status="degraded" if fallbacks else "success",
                documents=documents,
                requested_search_mode=requested_mode,
                actual_search_mode=actual_mode,
                embedding_attempts=embedding_attempts,
                tool_attempts=search_attempt,
                tool_failures=search_failures,
                fallbacks=fallbacks,
            )
        except Exception as exc:
            last_search_error = exc
            search_failures += 1
            logger.warning(
                "Search attempt %s/%s failed: %s",
                search_attempt,
                max_search_attempts,
                type(exc).__name__,
            )
            if search_attempt < max_search_attempts:
                await asyncio.sleep(0.25)

    return RetrievalOutcome(
        status="error",
        requested_search_mode=requested_mode,
        actual_search_mode="none",
        error_type=type(last_search_error).__name__ if last_search_error else "DeadlineExceeded",
        retryable=True,
        embedding_attempts=embedding_attempts,
        tool_attempts=search_failures,
        tool_failures=search_failures,
        fallbacks=fallbacks,
    )


def create_retriever_tool(
    opensearch_client: OpenSearchClient,
    embeddings_client: JinaEmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True,
):
    """Create a compatibility tool backed by the structured executor."""

    @tool
    async def retrieve_papers(query: str) -> list[Document]:
        """Search and return relevant arXiv research papers."""

        outcome = await execute_retrieval(
            query=query,
            opensearch_client=opensearch_client,
            embeddings_client=embeddings_client,
            top_k=top_k,
            use_hybrid=use_hybrid,
        )
        if outcome.status == "error":
            raise RetrievalUnavailableError(outcome.error_type or "retrieval unavailable")
        return outcome.documents

    return retrieve_papers
