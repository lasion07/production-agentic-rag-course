from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest
from airflow.dags.arxiv_ingestion.indexing import index_papers_hybrid


def test_zero_fetched_papers_is_successful_indexing_noop():
    database = MagicMock()
    database.get_session.return_value = nullcontext(MagicMock())
    task_instance = MagicMock()
    task_instance.xcom_pull.return_value = {
        "papers_fetched": 0,
        "papers_stored": 0,
        "stored_paper_ids": [],
        "indexable_paper_ids": [],
    }

    with patch(
        "airflow.dags.arxiv_ingestion.indexing.make_database",
        return_value=database,
    ):
        result = index_papers_hybrid(ti=task_instance)

    assert result["papers_processed"] == 0
    assert result["total_errors"] == 0


def test_fetched_papers_without_exact_storage_ids_fail_closed():
    database = MagicMock()
    database.get_session.return_value = nullcontext(MagicMock())
    task_instance = MagicMock()
    task_instance.xcom_pull.return_value = {
        "papers_fetched": 2,
        "papers_stored": 0,
        "stored_paper_ids": [],
        "indexable_paper_ids": [],
    }

    with (
        patch(
            "airflow.dags.arxiv_ingestion.indexing.make_database",
            return_value=database,
        ),
        pytest.raises(RuntimeError, match="exact indexable_paper_ids"),
    ):
        index_papers_hybrid(ti=task_instance)


def test_metadata_only_papers_are_not_sent_to_reconciliation():
    database = MagicMock()
    database.get_session.return_value = nullcontext(MagicMock())
    task_instance = MagicMock()
    task_instance.xcom_pull.return_value = {
        "papers_fetched": 2,
        "papers_stored": 2,
        "stored_paper_ids": ["paper-1", "paper-2"],
        "indexable_paper_ids": [],
    }

    with patch(
        "airflow.dags.arxiv_ingestion.indexing.make_database",
        return_value=database,
    ):
        result = index_papers_hybrid(ti=task_instance)

    assert result["papers_processed"] == 0
    assert result["papers_awaiting_content"] == 2
    assert result["total_errors"] == 0
