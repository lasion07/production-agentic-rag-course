import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session
from src.models.paper import Paper, PaperIndexStatus
from src.repositories.paper import PaperRepository

from .hybrid_indexer import HybridIndexingService

logger = logging.getLogger(__name__)

AlertCallback = Callable[[Paper, str], None]


def paper_to_index_data(paper: Paper) -> dict:
    """Freeze the source version and content used by one indexing attempt."""
    return {
        "id": str(paper.id),
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date,
        "raw_text": paper.raw_text,
        "sections": paper.sections,
        "source_version": paper.source_version,
    }


class IndexReconciler:
    """Heal PostgreSQL/OpenSearch drift using PostgreSQL as source of truth."""

    def __init__(
        self,
        indexing_service: HybridIndexingService,
        *,
        max_attempts: int = 3,
        retry_base_seconds: int = 300,
        lease_seconds: int = 900,
        batch_size: int = 100,
        alert_callback: Optional[AlertCallback] = None,
    ) -> None:
        self.indexing_service = indexing_service
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.lease_seconds = lease_seconds
        self.batch_size = batch_size
        self.alert_callback = alert_callback or self._log_dead_letter_alert

    async def reconcile(
        self,
        session: Session,
        *,
        paper_ids: Optional[Sequence[UUID]] = None,
    ) -> dict:
        repository = PaperRepository(session)
        papers_awaiting_content = 0
        if paper_ids is None:
            papers = repository.get_reconciliation_candidates(limit=self.batch_size)
        else:
            papers = repository.get_by_ids(list(paper_ids), for_update=True)
            found_ids = {paper.id for paper in papers}
            missing_ids = sorted(str(paper_id) for paper_id in set(paper_ids) - found_ids)
            if missing_ids:
                raise RuntimeError(f"Stored paper IDs missing from PostgreSQL: {missing_ids}")
            papers_awaiting_content = sum(
                1 for paper in papers if not paper.pdf_processed or not paper.raw_text
            )
            papers = [
                paper
                for paper in papers
                if paper.source_version > paper.indexed_version
                and paper.pdf_processed
                and paper.raw_text
                and paper.index_status != PaperIndexStatus.DEAD_LETTER.value
                and self._is_due(paper)
            ]

        totals = {
            "papers_processed": 0,
            "papers_indexed": 0,
            "papers_retry_pending": 0,
            "papers_dead_letter": 0,
            "papers_awaiting_content": papers_awaiting_content,
            "total_chunks_created": 0,
            "total_chunks_indexed": 0,
            "total_embeddings_generated": 0,
            "total_errors": 0,
            "results": [],
        }

        claims = []
        for paper in papers:
            paper_id = paper.id
            source_version = int(paper.source_version)
            totals["papers_processed"] += 1
            claim_token = repository.mark_indexing(
                paper,
                source_version=source_version,
                lease_seconds=self.lease_seconds,
            )
            claims.append(
                (
                    paper_id,
                    source_version,
                    claim_token,
                    paper.arxiv_id,
                    paper_to_index_data(paper),
                )
            )
        if claims:
            session.commit()

        for paper_id, source_version, claim_token, arxiv_id, index_data in claims:
            try:
                stats = await self.indexing_service.reindex_paper(
                    arxiv_id,
                    index_data,
                )
                if (
                    stats["errors"] > 0
                    or stats["chunks_created"] == 0
                    or stats["chunks_indexed"] != stats["chunks_created"]
                ):
                    raise RuntimeError(
                        "Incomplete OpenSearch replacement: "
                        f"created={stats['chunks_created']} indexed={stats['chunks_indexed']} "
                        f"errors={stats['errors']}"
                    )

                current = repository.get_by_id(paper_id)
                if current is None:
                    raise RuntimeError(f"Paper {paper_id} disappeared during indexing")
                repository.mark_indexed(
                    current,
                    source_version=source_version,
                    claim_token=claim_token,
                )
                session.commit()

                totals["papers_indexed"] += 1
                totals["total_chunks_created"] += stats["chunks_created"]
                totals["total_chunks_indexed"] += stats["chunks_indexed"]
                totals["total_embeddings_generated"] += stats["embeddings_generated"]
                totals["results"].append(
                    {
                        "paper_id": str(paper_id),
                        "source_version": source_version,
                        "status": PaperIndexStatus.INDEXED.value,
                    }
                )
            except Exception as exc:
                session.rollback()
                current = repository.get_by_id(paper_id)
                if current is None:
                    logger.exception("Cannot persist indexing failure for missing paper %s", paper_id)
                    totals["total_errors"] += 1
                    continue

                if current.index_claim_token != claim_token:
                    totals.setdefault("papers_superseded", 0)
                    totals["papers_superseded"] += 1
                    totals["results"].append(
                        {
                            "paper_id": str(paper_id),
                            "source_version": source_version,
                            "status": "superseded",
                        }
                    )
                    logger.info(
                        "Ignoring superseded indexing worker paper_id=%s version=%s",
                        paper_id,
                        source_version,
                    )
                    continue

                delay_seconds = self.retry_base_seconds * (2 ** max(current.index_attempts - 1, 0))
                next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
                repository.mark_index_failed(
                    current,
                    error=exc,
                    max_attempts=self.max_attempts,
                    next_retry_at=next_retry_at,
                    claim_token=claim_token,
                )
                session.commit()

                totals["total_errors"] += 1
                if current.index_status == PaperIndexStatus.DEAD_LETTER.value:
                    totals["papers_dead_letter"] += 1
                    self.alert_callback(current, current.last_index_error or "unknown indexing error")
                else:
                    totals["papers_retry_pending"] += 1
                totals["results"].append(
                    {
                        "paper_id": str(paper_id),
                        "source_version": source_version,
                        "status": current.index_status,
                    }
                )

        return totals

    @staticmethod
    def _log_dead_letter_alert(paper: Paper, error: str) -> None:
        logger.critical(
            "INDEX_RECONCILIATION_DLQ paper_id=%s arxiv_id=%s source_version=%s error=%s",
            paper.id,
            paper.arxiv_id,
            paper.source_version,
            error,
        )

    @staticmethod
    def _is_due(paper: Paper) -> bool:
        now = datetime.now(timezone.utc)
        if paper.index_status in {
            PaperIndexStatus.PENDING.value,
            PaperIndexStatus.INDEXED.value,
        }:
            return True
        if paper.index_status == PaperIndexStatus.RETRY_PENDING.value:
            return paper.next_index_retry_at is not None and paper.next_index_retry_at <= now
        if paper.index_status == PaperIndexStatus.INDEXING.value:
            return paper.index_lease_expires_at is not None and paper.index_lease_expires_at <= now
        return False
