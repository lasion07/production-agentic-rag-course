from types import SimpleNamespace
from unittest.mock import Mock

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
