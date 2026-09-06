from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airflow.dags.arxiv_ingestion.setup import setup_environment


def test_production_ingestion_setup_requires_preprovisioned_index_without_mutating_schema():
    database = MagicMock()
    database.get_session.return_value = nullcontext(MagicMock())
    opensearch = MagicMock(
        index_name="arxiv-papers-chunks-read",
        read_alias="arxiv-papers-chunks-read",
        write_alias="arxiv-papers-chunks-write",
    )
    opensearch.client.cluster.health.return_value = {"status": "green"}
    opensearch.client.indices.exists.return_value = True
    opensearch.client.indices.exists_alias.return_value = True
    opensearch.client.indices.get_alias.side_effect = [
        {"arxiv-papers-chunks-v1": {}},
        {"arxiv-papers-chunks-v1": {}},
    ]
    services = (SimpleNamespace(base_url="https://export.arxiv.org"), None, database, None, opensearch)

    with (
        patch(
            "airflow.dags.arxiv_ingestion.setup.get_cached_services",
            return_value=services,
        ),
    ):
        result = setup_environment()

    assert result["status"] == "success"
    opensearch.setup_indices.assert_not_called()
    opensearch.client.transport.perform_request.assert_called_once_with(
        "GET",
        "/_search/pipeline/hybrid-rrf-pipeline",
    )
    opensearch.client.indices.exists.assert_called_once_with(
        index="arxiv-papers-chunks-read"
    )
