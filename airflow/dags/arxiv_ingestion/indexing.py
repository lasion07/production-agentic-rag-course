import asyncio
import logging
from uuid import UUID

from src.config import get_settings
from src.db.factory import make_database
from src.services.indexing.factory import make_hybrid_indexing_service
from src.services.indexing.reconciliation import IndexReconciler
from src.services.opensearch.factory import make_opensearch_client_fresh

logger = logging.getLogger(__name__)


async def _run_reconciliation(session, paper_ids=None):
    settings = get_settings()
    reconciler = IndexReconciler(
        make_hybrid_indexing_service(settings),
        max_attempts=settings.index_reconciliation_max_attempts,
        retry_base_seconds=settings.index_reconciliation_retry_base_seconds,
        lease_seconds=settings.index_reconciliation_lease_seconds,
        batch_size=settings.index_reconciliation_batch_size,
    )
    return await reconciler.reconcile(session, paper_ids=paper_ids)


def index_papers_hybrid(**context):
    """Index papers with chunking and vector embeddings for hybrid search.

    This task:
    1. Fetches recently processed papers from PostgreSQL
    2. Chunks them into overlapping segments (600 words, 100 overlap)
    3. Generates embeddings using Jina AI
    4. Indexes chunks with embeddings into OpenSearch
    """
    try:
        database = make_database()

        ti = context.get("ti")

        fetch_results = None
        if ti:
            fetch_results = ti.xcom_pull(task_ids="fetch_daily_papers", key="fetch_results")

        with database.get_session() as session:
            paper_ids = (fetch_results or {}).get("indexable_paper_ids", [])
            if not paper_ids:
                if fetch_results and fetch_results.get("papers_stored", 0) > 0:
                    logger.info(
                        "Stored papers contain no parsed content; exact-ID indexing is a successful no-op"
                    )
                    return {
                        "papers_processed": 0,
                        "papers_indexed": 0,
                        "papers_awaiting_content": fetch_results["papers_stored"],
                        "total_chunks_created": 0,
                        "total_chunks_indexed": 0,
                        "total_embeddings_generated": 0,
                        "total_errors": 0,
                    }
                if fetch_results and fetch_results.get("papers_fetched", 0) == 0:
                    logger.info("No papers fetched; exact-ID indexing is a successful no-op")
                    return {
                        "papers_processed": 0,
                        "papers_indexed": 0,
                        "total_chunks_created": 0,
                        "total_chunks_indexed": 0,
                        "total_embeddings_generated": 0,
                        "total_errors": 0,
                    }
                raise RuntimeError("Indexing requires exact indexable_paper_ids from ingestion")
            stable_ids = [UUID(value) for value in paper_ids]
            logger.info(f"Indexing {len(stable_ids)} exact papers for hybrid search")
            stats = asyncio.run(_run_reconciliation(session, stable_ids))

            logger.info(
                f"Hybrid indexing complete: {stats['papers_processed']} papers, "
                f"{stats['total_chunks_created']} chunks created, "
                f"{stats['total_chunks_indexed']} chunks indexed"
            )

            if ti:
                ti.xcom_push(key="hybrid_index_stats", value=stats)

            if stats["total_errors"]:
                raise RuntimeError(
                    f"Hybrid indexing left {stats['total_errors']} paper(s) inconsistent"
                )

            return stats

    except Exception as e:
        logger.error(f"Failed to index papers for hybrid search: {e}")
        raise


def reconcile_index_consistency(**context):
    """Periodic worker that heals due PostgreSQL/OpenSearch inconsistencies."""
    database = make_database()
    with database.get_session() as session:
        stats = asyncio.run(_run_reconciliation(session))

    logger.info(
        "Reconciliation complete: processed=%s indexed=%s retry_pending=%s dead_letter=%s",
        stats["papers_processed"],
        stats["papers_indexed"],
        stats["papers_retry_pending"],
        stats["papers_dead_letter"],
    )
    ti = context.get("ti")
    if ti:
        ti.xcom_push(key="reconciliation_stats", value=stats)
    return stats


def verify_hybrid_index(**context):
    """Verify hybrid index health and get statistics."""
    try:
        opensearch_client = make_opensearch_client_fresh()

        stats = opensearch_client.client.indices.stats(index=opensearch_client.index_name)

        count = opensearch_client.client.count(index=opensearch_client.index_name)

        paper_count_query = {"aggs": {"unique_papers": {"cardinality": {"field": "arxiv_id"}}}, "size": 0}

        paper_count_response = opensearch_client.client.search(index=opensearch_client.index_name, body=paper_count_query)

        unique_papers = paper_count_response["aggregations"]["unique_papers"]["value"]

        result = {
            "index_name": opensearch_client.index_name,
            "total_chunks": count["count"],
            "unique_papers": unique_papers,
            "avg_chunks_per_paper": (count["count"] / unique_papers if unique_papers > 0 else 0),
            "index_size_mb": stats["indices"][opensearch_client.index_name]["total"]["store"]["size_in_bytes"] / (1024 * 1024),
        }

        logger.info(
            f"Hybrid index stats: {result['total_chunks']} chunks, "
            f"{result['unique_papers']} papers, "
            f"{result['avg_chunks_per_paper']:.1f} chunks/paper"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to verify hybrid index: {e}")
        raise
