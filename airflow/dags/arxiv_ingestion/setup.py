import logging

from sqlalchemy import text
from src.services.opensearch.index_config_hybrid import HYBRID_RRF_PIPELINE

from .common import get_cached_services

logger = logging.getLogger(__name__)


def setup_environment():
    """Setup environment and verify dependencies.

    Creates hybrid search index with RRF pipeline.
    """
    logger.info("Setting up environment for arXiv paper ingestion")

    try:
        arxiv_client, _pdf_parser, database, _metadata_fetcher, opensearch_client = get_cached_services()

        with database.get_session() as session:
            session.execute(text("SELECT 1"))
            logger.info("Database connection verified")

        try:
            health = opensearch_client.client.cluster.health()
            if health["status"] in ["green", "yellow", "red"]:
                logger.info(f"OpenSearch hybrid client connected (cluster status: {health['status']})")
            else:
                raise Exception(f"OpenSearch cluster unhealthy: {health['status']}")
        except Exception as e:
            raise Exception(f"OpenSearch hybrid client connection failed: {e}")

        read_alias_exists = opensearch_client.client.indices.exists_alias(
            name=opensearch_client.read_alias
        )
        write_alias_exists = opensearch_client.client.indices.exists_alias(
            name=opensearch_client.write_alias
        )
        if not read_alias_exists or not write_alias_exists:
            raise RuntimeError("Required OpenSearch read/write aliases are not provisioned")
        read_targets = set(
            opensearch_client.client.indices.get_alias(name=opensearch_client.read_alias)
        )
        write_targets = set(
            opensearch_client.client.indices.get_alias(name=opensearch_client.write_alias)
        )
        index_exists = opensearch_client.client.indices.exists(
            index=opensearch_client.index_name
        )
        if not index_exists or read_targets != write_targets or len(read_targets) != 1:
            raise RuntimeError(
                "OpenSearch aliases must resolve to the same single physical index"
            )
        opensearch_client.client.transport.perform_request(
            "GET",
            f"/_search/pipeline/{HYBRID_RRF_PIPELINE['id']}",
        )
        logger.info("OpenSearch aliases and RRF pipeline are pre-provisioned")

        logger.info("Hybrid search setup completed")

        logger.info(f"arXiv client ready: {arxiv_client.base_url}")
        logger.info("PDF parser service ready (Docling models cached)")

        return {"status": "success", "message": "Environment setup completed"}

    except Exception as e:
        error_msg = f"Environment setup failed: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
