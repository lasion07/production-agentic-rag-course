import logging

from fastapi import APIRouter
from src.api_errors import PUBLIC_ERROR_RESPONSES, PublicAPIError
from src.dependencies import EmbeddingsDep, OpenSearchDep
from src.schemas.api.search import HybridSearchRequest, SearchHit, SearchResponse
from src.security import APIIdentityDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hybrid-search", tags=["hybrid-search"], responses=PUBLIC_ERROR_RESPONSES)


@router.post("/", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    opensearch_client: OpenSearchDep,
    embeddings_service: EmbeddingsDep,
    _identity: APIIdentityDep,
) -> SearchResponse:
    """
    Hybrid search endpoint supporting multiple search modes.
    """
    try:
        if not opensearch_client.health_check():
            raise PublicAPIError(503, "retrieval_unavailable", "Search is temporarily unavailable.")

        query_embedding = None
        if request.use_hybrid:
            try:
                query_embedding = await embeddings_service.embed_query(request.query)
                logger.info("Generated query embedding for hybrid search")
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
                query_embedding = None

        logger.info("Hybrid search started hybrid=%s", request.use_hybrid and query_embedding is not None)

        results = opensearch_client.search_unified(
            query=request.query,
            query_embedding=query_embedding,
            size=request.size,
            from_=request.from_,
            categories=request.categories,
            latest=request.latest_papers,
            use_hybrid=request.use_hybrid,
            min_score=request.min_score,
        )

        hits = []
        for hit in results.get("hits", []):
            hits.append(
                SearchHit(
                    arxiv_id=hit.get("arxiv_id", ""),
                    title=hit.get("title", ""),
                    authors=hit.get("authors"),
                    abstract=hit.get("abstract"),
                    published_date=hit.get("published_date"),
                    pdf_url=hit.get("pdf_url"),
                    score=hit.get("score", 0.0),
                    highlights=hit.get("highlights"),
                    chunk_text=hit.get("chunk_text"),
                    chunk_id=hit.get("chunk_id"),
                    section_name=hit.get("section_name"),
                )
            )

        search_response = SearchResponse(
            query=request.query,
            total=results.get("total", 0),
            hits=hits,
            size=request.size,
            **{"from": request.from_},
            search_mode="hybrid" if (request.use_hybrid and query_embedding) else "bm25",
        )

        logger.info(f"Search completed: {search_response.total} results returned")
        return search_response

    except PublicAPIError:
        raise
    except Exception as exc:
        logger.exception("Hybrid search failed")
        raise PublicAPIError(500, "internal_error", "Search could not be completed.") from exc
