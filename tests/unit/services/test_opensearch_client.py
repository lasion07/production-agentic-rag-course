from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.services.opensearch.client import OpenSearchClient


def test_hybrid_search_fuses_more_candidates_than_final_k():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.index_name = "papers-chunks"
    client.settings = SimpleNamespace(
        opensearch=SimpleNamespace(hybrid_search_size_multiplier=4)
    )
    client.client = Mock()
    client.client.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_id": "chunk-1",
                    "_score": 1.0,
                    "_source": {
                        "arxiv_id": "paper-1",
                        "chunk_text": "quantitative evidence",
                    },
                }
            ],
        }
    }

    result = client._search_hybrid_native(
        query="reported success range",
        query_embedding=[0.1, 0.2],
        size=3,
        categories=None,
        min_score=0.0,
    )

    body = client.client.search.call_args.kwargs["body"]
    hybrid = body["query"]["hybrid"]
    assert body["size"] == 3
    assert hybrid["pagination_depth"] == 12
    assert hybrid["queries"][1]["knn"]["embedding"]["k"] == 12
    assert result["hits"][0]["chunk_id"] == "chunk-1"


def test_bulk_index_routes_writes_through_write_alias():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.index_name = "papers-chunks-read"
    client.write_alias = "papers-chunks-write"
    client.client = Mock()

    with patch("opensearchpy.helpers.bulk", return_value=(1, [])) as bulk:
        client.bulk_index_chunks(
            [
                {
                    "document_id": "paper-1:v1:c0",
                    "chunk_data": {"chunk_text": "evidence"},
                    "embedding": [0.1, 0.2],
                }
            ]
        )

    assert bulk.call_args.args[1][0]["_index"] == "papers-chunks-write"


def test_index_stats_aggregates_physical_indices_behind_alias():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.index_name = "papers-chunks-read"
    client.client = Mock()
    client.client.indices.exists.return_value = True
    client.client.indices.stats.return_value = {
        "indices": {
            "papers-chunks-v2": {
                "total": {
                    "docs": {"count": 11, "deleted": 2},
                    "store": {"size_in_bytes": 1024},
                }
            }
        }
    }

    result = client.get_index_stats()

    assert result["backing_indices"] == ["papers-chunks-v2"]
    assert result["document_count"] == 11
    assert result["deleted_count"] == 2


def test_rrf_pipeline_setup_is_idempotent_on_search_pipeline_endpoint():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.client = Mock()
    client.client.transport.perform_request.return_value = {
        "hybrid-rrf-pipeline": {"description": "existing"}
    }

    created = client._create_rrf_pipeline(force=False)

    assert created is False
    client.client.transport.perform_request.assert_called_once_with(
        "GET",
        "/_search/pipeline/hybrid-rrf-pipeline",
    )
