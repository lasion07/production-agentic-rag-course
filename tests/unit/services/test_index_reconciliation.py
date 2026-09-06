import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models.paper import Paper, PaperIndexStatus
from src.services.indexing.hybrid_indexer import (
    HybridIndexingService,
    build_chunk_document_id,
)
from src.services.indexing.reconciliation import IndexReconciler
from src.services.opensearch.client import OpenSearchClient


def make_paper(*, source_version: int = 2, indexed_version: int = 1) -> Paper:
    return Paper(
        id=uuid.uuid4(),
        arxiv_id="2401.00001v1",
        title="Paper",
        authors=["Author"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date="2024-01-01T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2401.00001v1",
        raw_text="Evidence text",
        sections=[],
        pdf_processed=True,
        source_version=source_version,
        indexed_version=indexed_version,
        index_status=PaperIndexStatus.PENDING.value,
        index_attempts=0,
    )


def complete_stats() -> dict:
    return {
        "chunks_created": 2,
        "chunks_indexed": 2,
        "embeddings_generated": 2,
        "errors": 0,
    }


def test_chunk_document_identity_is_deterministic_and_versioned():
    first = build_chunk_document_id(paper_id="paper-123", source_version=7, chunk_index=2)
    replay = build_chunk_document_id(paper_id="paper-123", source_version=7, chunk_index=2)
    next_version = build_chunk_document_id(
        paper_id="paper-123", source_version=8, chunk_index=2
    )

    assert first == replay == "paper-123:v7:c2"
    assert next_version != first


def test_bulk_index_uses_deterministic_document_id():
    client = OpenSearchClient.__new__(OpenSearchClient)
    client.client = MagicMock()
    client.index_name = "papers-chunks"
    chunks = [
        {
            "document_id": "paper-123:v7:c2",
            "chunk_data": {"chunk_id": "paper-123:v7:c2", "chunk_text": "evidence"},
            "embedding": [0.1, 0.2],
        }
    ]

    with patch("opensearchpy.helpers.bulk", return_value=(1, [])) as bulk:
        result = client.bulk_index_chunks(chunks)
        replay_result = client.bulk_index_chunks(chunks)

    first_actions = bulk.call_args_list[0].args[1]
    replay_actions = bulk.call_args_list[1].args[1]
    assert first_actions[0]["_id"] == replay_actions[0]["_id"] == "paper-123:v7:c2"
    assert result == {"success": 1, "failed": 0}
    assert replay_result == result


@pytest.mark.asyncio
async def test_partial_replacement_never_deletes_last_good_version():
    chunk = SimpleNamespace(
        arxiv_id="2401.00001v1",
        paper_id="paper-123",
        text="evidence",
        metadata=SimpleNamespace(
            chunk_index=0,
            word_count=1,
            start_char=0,
            end_char=8,
            section_title="Method",
        ),
    )
    chunker = MagicMock()
    chunker.chunk_paper.return_value = [chunk]
    embeddings = MagicMock()
    embeddings.embed_passages = AsyncMock(return_value=[[0.1, 0.2]])
    opensearch = MagicMock()
    opensearch.bulk_index_chunks.return_value = {"success": 0, "failed": 1}
    service = HybridIndexingService(chunker, embeddings, opensearch)

    stats = await service.reindex_paper(
        "2401.00001v1",
        {
            "id": "paper-123",
            "arxiv_id": "2401.00001v1",
            "source_version": 2,
            "raw_text": "evidence",
        },
    )

    assert stats["errors"] == 1
    opensearch.delete_paper_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_complete_replacement_cleans_old_version_only_after_success():
    chunk = SimpleNamespace(
        arxiv_id="2401.00001v1",
        paper_id="paper-123",
        text="evidence",
        metadata=SimpleNamespace(
            chunk_index=0,
            word_count=1,
            start_char=0,
            end_char=8,
            section_title="Method",
        ),
    )
    chunker = MagicMock()
    chunker.chunk_paper.return_value = [chunk]
    embeddings = MagicMock()
    embeddings.embed_passages = AsyncMock(return_value=[[0.1, 0.2]])
    opensearch = MagicMock()
    opensearch.bulk_index_chunks.return_value = {"success": 1, "failed": 0}
    service = HybridIndexingService(chunker, embeddings, opensearch)

    stats = await service.reindex_paper(
        "2401.00001v1",
        {
            "id": "paper-123",
            "arxiv_id": "2401.00001v1",
            "source_version": 2,
            "raw_text": "evidence",
        },
    )

    assert stats["errors"] == 0
    opensearch.delete_paper_chunks.assert_called_once_with(
        "2401.00001v1", before_version=2
    )


@pytest.mark.asyncio
async def test_live_indexing_lease_prevents_duplicate_worker_claim():
    paper = make_paper()
    paper.index_status = PaperIndexStatus.INDEXING.value
    paper.index_lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    session = MagicMock()
    session.scalars.return_value = [paper]
    indexing = MagicMock()
    indexing.reindex_paper = AsyncMock(return_value=complete_stats())

    result = await IndexReconciler(indexing).reconcile(session, paper_ids=[paper.id])

    assert result["papers_processed"] == 0
    indexing.reindex_paper.assert_not_awaited()


@pytest.mark.asyncio
async def test_version_drift_is_reconciled_even_when_status_claims_indexed():
    paper = make_paper(source_version=3, indexed_version=2)
    paper.index_status = PaperIndexStatus.INDEXED.value
    session = MagicMock()
    session.scalars.return_value = [paper]
    session.scalar.return_value = paper
    indexing = MagicMock()
    indexing.reindex_paper = AsyncMock(return_value=complete_stats())

    result = await IndexReconciler(indexing).reconcile(session, paper_ids=[paper.id])

    assert result["papers_indexed"] == 1
    assert paper.indexed_version == 3


@pytest.mark.asyncio
async def test_reconciler_marks_complete_version_indexed():
    paper = make_paper()
    session = MagicMock()
    session.scalars.return_value = [paper]
    session.scalar.return_value = paper
    indexing = MagicMock()
    indexing.reindex_paper = AsyncMock(return_value=complete_stats())
    reconciler = IndexReconciler(indexing)

    result = await reconciler.reconcile(session, paper_ids=[paper.id])

    assert result["papers_indexed"] == 1
    assert result["total_errors"] == 0
    assert paper.indexed_version == 2
    assert paper.index_status == PaperIndexStatus.INDEXED.value
    assert session.commit.call_count == 2


@pytest.mark.asyncio
async def test_reconciler_ignores_worker_superseded_by_newer_ingestion():
    paper = make_paper()
    session = MagicMock()
    session.scalars.return_value = [paper]
    session.scalar.return_value = paper

    async def finish_after_new_ingestion(*_args, **_kwargs):
        paper.source_version = 3
        paper.index_status = PaperIndexStatus.PENDING.value
        paper.index_claim_token = None
        return complete_stats()

    indexing = MagicMock()
    indexing.reindex_paper = AsyncMock(side_effect=finish_after_new_ingestion)

    result = await IndexReconciler(indexing).reconcile(session, paper_ids=[paper.id])

    assert result["papers_superseded"] == 1
    assert result["papers_indexed"] == 0
    assert result["total_errors"] == 0
    assert paper.indexed_version == 1
    assert paper.source_version == 3
    assert paper.index_status == PaperIndexStatus.PENDING.value


@pytest.mark.asyncio
async def test_reconciler_retries_then_dead_letters_and_alerts():
    paper = make_paper()
    session = MagicMock()
    session.scalars.return_value = [paper]
    session.scalar.return_value = paper
    indexing = MagicMock()
    indexing.reindex_paper = AsyncMock(
        return_value={
            "chunks_created": 2,
            "chunks_indexed": 1,
            "embeddings_generated": 2,
            "errors": 1,
        }
    )
    alert = MagicMock()
    reconciler = IndexReconciler(
        indexing,
        max_attempts=2,
        retry_base_seconds=1,
        alert_callback=alert,
    )

    first = await reconciler.reconcile(session, paper_ids=[paper.id])
    paper.next_index_retry_at = paper.last_index_attempt_at
    second = await reconciler.reconcile(session, paper_ids=[paper.id])

    assert first["papers_retry_pending"] == 1
    assert second["papers_dead_letter"] == 1
    assert paper.index_attempts == 2
    assert paper.index_status == PaperIndexStatus.DEAD_LETTER.value
    assert "Incomplete OpenSearch replacement" in paper.last_index_error
    assert "\n" not in paper.last_index_error
    alert.assert_called_once()
