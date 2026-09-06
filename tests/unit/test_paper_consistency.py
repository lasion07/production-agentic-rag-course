from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from src.exceptions import StaleIndexClaimError
from src.models.paper import Paper, PaperIndexStatus
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate
from src.services.metadata_fetcher import MetadataFetcher


def paper_create(*, processed: bool, title: str = "Updated title") -> PaperCreate:
    return PaperCreate(
        arxiv_id="2401.00001v1",
        title=title,
        authors=["Author"],
        abstract="Updated abstract",
        categories=["cs.AI"],
        published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        pdf_url="https://arxiv.org/pdf/2401.00001v1",
        raw_text="new parsed text" if processed else None,
        sections=[] if processed else None,
        parser_used="docling" if processed else None,
        parser_metadata={"ok": True} if processed else {"note": "parse failed"},
        pdf_processed=processed,
        pdf_processing_date=datetime.now(timezone.utc) if processed else None,
    )


def arxiv_paper(arxiv_id: str) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=f"Paper {arxiv_id}",
        authors=["Author"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date="2024-01-01T00:00:00Z",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )


def test_repository_does_not_commit_caller_owned_transaction():
    session = MagicMock()
    session.scalar.return_value = None
    repository = PaperRepository(session)

    repository.upsert(paper_create(processed=True))

    session.flush.assert_called_once()
    session.commit.assert_not_called()


def test_failed_parse_does_not_overwrite_last_good_content():
    existing = Paper(
        **paper_create(processed=True, title="Original title").model_dump(),
    )
    session = MagicMock()
    session.scalar.return_value = existing
    repository = PaperRepository(session)

    repository.upsert(paper_create(processed=False))

    assert existing.title == "Updated title"
    assert existing.pdf_processed is True
    assert existing.raw_text == "new parsed text"
    assert existing.parser_metadata == {"ok": True}
    session.commit.assert_not_called()


def test_changed_retrieval_content_bumps_source_version_and_resets_retry_state():
    existing = Paper(
        **paper_create(processed=True, title="Original title").model_dump(),
        source_version=7,
        indexed_version=7,
        index_status=PaperIndexStatus.INDEXED.value,
        index_attempts=3,
        last_index_error="old failure",
    )
    session = MagicMock()
    session.scalar.return_value = existing

    PaperRepository(session).upsert(paper_create(processed=True, title="Updated title"))

    assert existing.source_version == 8
    assert existing.indexed_version == 7
    assert existing.index_status == PaperIndexStatus.PENDING.value
    assert existing.index_attempts == 0
    assert existing.last_index_error is None


def test_duplicate_delivery_does_not_bump_source_version():
    payload = paper_create(processed=True)
    existing = Paper(
        **payload.model_dump(),
        source_version=4,
        indexed_version=4,
        index_status=PaperIndexStatus.INDEXED.value,
        index_attempts=1,
    )
    session = MagicMock()
    session.scalar.return_value = existing

    PaperRepository(session).upsert(payload)

    assert existing.source_version == 4
    assert existing.index_status == PaperIndexStatus.INDEXED.value


def test_periodic_reconciliation_query_excludes_metadata_only_rows():
    session = MagicMock()
    session.scalars.return_value = []

    PaperRepository(session).get_reconciliation_candidates()

    statement = str(session.scalars.call_args.args[0])
    assert "papers.pdf_processed IS true" in statement
    assert "papers.raw_text IS NOT NULL" in statement


def test_old_attempt_acknowledgement_cannot_hide_newer_source_version():
    paper = Paper(
        **paper_create(processed=True).model_dump(),
        source_version=3,
        indexed_version=1,
        index_status=PaperIndexStatus.INDEXING.value,
        index_attempts=1,
    )
    session = MagicMock()

    paper.index_claim_token = "claim-1"
    PaperRepository(session).mark_indexed(
        paper,
        source_version=2,
        claim_token="claim-1",
    )

    assert paper.indexed_version == 2
    assert paper.source_version == 3
    assert paper.index_status == PaperIndexStatus.PENDING.value


def test_superseded_claim_cannot_acknowledge_newer_ingestion():
    paper = Paper(
        **paper_create(processed=True).model_dump(),
        source_version=3,
        indexed_version=1,
        index_status=PaperIndexStatus.PENDING.value,
        index_claim_token=None,
    )
    session = MagicMock()

    with pytest.raises(StaleIndexClaimError):
        PaperRepository(session).mark_indexed(
            paper,
            source_version=2,
            claim_token="superseded-claim",
        )

    assert paper.indexed_version == 1
    assert paper.index_status == PaperIndexStatus.PENDING.value


def test_batch_rolls_back_only_failed_paper_and_continues():
    fetcher = MetadataFetcher(MagicMock(), MagicMock())
    session = MagicMock()
    papers = [arxiv_paper(f"2401.0000{number}v1") for number in range(1, 4)]
    storage_errors = []
    repository = MagicMock()
    repository.upsert.side_effect = [
        MagicMock(id="paper-1"),
        RuntimeError("database write failed"),
        MagicMock(id="paper-3"),
    ]

    with patch("src.services.metadata_fetcher.PaperRepository", return_value=repository):
        stored = fetcher._store_papers_to_db(
            papers,
            {},
            session,
            storage_errors=storage_errors,
        )

    assert stored == {
        "stored_paper_ids": ["paper-1", "paper-3"],
        "indexable_paper_ids": [],
    }
    assert session.commit.call_count == 2
    session.rollback.assert_called_once()
    assert storage_errors == ["Database storage failed: 2401.00002v1"]
