from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from src.exceptions import StaleIndexClaimError
from src.models.paper import Paper, PaperIndexStatus
from src.schemas.arxiv.paper import PaperCreate


class PaperRepository:
    INDEX_RELEVANT_FIELDS = frozenset(
        {
            "title",
            "authors",
            "abstract",
            "categories",
            "published_date",
            "pdf_url",
            "raw_text",
            "sections",
            "references",
            "parser_used",
        }
    )

    def __init__(self, session: Session):
        self.session = session

    def create(self, paper: PaperCreate) -> Paper:
        db_paper = Paper(
            **paper.model_dump(),
            source_version=1,
            indexed_version=0,
            index_status=PaperIndexStatus.PENDING.value,
            index_attempts=0,
        )
        self.session.add(db_paper)
        self.session.flush()
        self.session.refresh(db_paper)
        return db_paper

    def get_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
        return self.session.scalar(stmt)

    def get_by_id(self, paper_id: UUID) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.id == paper_id)
        return self.session.scalar(stmt)

    def get_by_ids(self, paper_ids: List[UUID], *, for_update: bool = False) -> List[Paper]:
        if not paper_ids:
            return []
        stmt = select(Paper).where(Paper.id.in_(paper_ids))
        if for_update:
            stmt = stmt.with_for_update()
        return list(self.session.scalars(stmt))

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_count(self) -> int:
        stmt = select(func.count(Paper.id))
        return self.session.scalar(stmt) or 0

    def get_processed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have been successfully processed with PDF content."""
        stmt = (
            select(Paper)
            .where(Paper.pdf_processed == True)
            .order_by(Paper.pdf_processing_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def get_unprocessed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that haven't been processed for PDF content yet."""
        stmt = select(Paper).where(Paper.pdf_processed == False).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_papers_with_raw_text(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have raw text content stored."""
        stmt = select(Paper).where(Paper.raw_text != None).order_by(Paper.pdf_processing_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_processing_stats(self) -> dict:
        """Get statistics about PDF processing status."""
        total_papers = self.get_count()

        # Count processed papers
        processed_stmt = select(func.count(Paper.id)).where(Paper.pdf_processed == True)
        processed_papers = self.session.scalar(processed_stmt) or 0

        # Count papers with text
        text_stmt = select(func.count(Paper.id)).where(Paper.raw_text != None)
        papers_with_text = self.session.scalar(text_stmt) or 0

        return {
            "total_papers": total_papers,
            "processed_papers": processed_papers,
            "papers_with_text": papers_with_text,
            "processing_rate": (processed_papers / total_papers * 100) if total_papers > 0 else 0,
            "text_extraction_rate": (papers_with_text / processed_papers * 100) if processed_papers > 0 else 0,
        }

    def update(self, paper: Paper) -> Paper:
        self.session.add(paper)
        self.session.flush()
        self.session.refresh(paper)
        return paper

    def upsert(self, paper_create: PaperCreate) -> Paper:
        # Check if paper already exists
        existing_paper = self.get_by_arxiv_id(paper_create.arxiv_id)
        if existing_paper:
            update_data = paper_create.model_dump(exclude_unset=True)

            # A metadata-only retry or failed parse must never downgrade the
            # last successfully parsed representation.
            if existing_paper.pdf_processed and not paper_create.pdf_processed:
                for field_name in (
                    "raw_text",
                    "sections",
                    "references",
                    "parser_used",
                    "parser_metadata",
                    "pdf_processed",
                    "pdf_processing_date",
                ):
                    update_data.pop(field_name, None)

            content_changed = any(
                getattr(existing_paper, field_name) != value
                for field_name, value in update_data.items()
                if field_name in self.INDEX_RELEVANT_FIELDS
            )
            for key, value in update_data.items():
                setattr(existing_paper, key, value)
            if content_changed:
                existing_paper.source_version = int(existing_paper.source_version or 1) + 1
                existing_paper.index_status = PaperIndexStatus.PENDING.value
                existing_paper.index_attempts = 0
                existing_paper.last_index_error = None
                existing_paper.index_claim_token = None
                existing_paper.index_lease_expires_at = None
                existing_paper.next_index_retry_at = None
            return self.update(existing_paper)
        else:
            # Create new paper
            return self.create(paper_create)

    def get_reconciliation_candidates(
        self,
        *,
        limit: int = 100,
        now: Optional[datetime] = None,
    ) -> List[Paper]:
        now = now or datetime.now(timezone.utc)
        stmt = (
            select(Paper)
            .where(
                Paper.source_version > Paper.indexed_version,
                Paper.pdf_processed.is_(True),
                Paper.raw_text.is_not(None),
                Paper.index_status != PaperIndexStatus.DEAD_LETTER.value,
                or_(
                    Paper.index_status == PaperIndexStatus.PENDING.value,
                    Paper.index_status == PaperIndexStatus.INDEXED.value,
                    and_(
                        Paper.index_status == PaperIndexStatus.RETRY_PENDING.value,
                        Paper.next_index_retry_at <= now,
                    ),
                    and_(
                        Paper.index_status == PaperIndexStatus.INDEXING.value,
                        Paper.index_lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(Paper.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(stmt))

    def mark_indexing(
        self,
        paper: Paper,
        *,
        source_version: int,
        lease_seconds: int,
    ) -> str:
        if paper.source_version != source_version:
            raise ValueError("Cannot index a stale source version")
        paper.index_status = PaperIndexStatus.INDEXING.value
        paper.index_attempts = int(paper.index_attempts or 0) + 1
        claim_token = str(uuid4())
        paper.index_claim_token = claim_token
        now = datetime.now(timezone.utc)
        paper.last_index_attempt_at = now
        paper.index_lease_expires_at = now + timedelta(seconds=lease_seconds)
        paper.next_index_retry_at = None
        self.session.flush()
        return claim_token

    def mark_indexed(
        self,
        paper: Paper,
        *,
        source_version: int,
        claim_token: str,
    ) -> None:
        if paper.index_claim_token != claim_token:
            raise StaleIndexClaimError("Index claim was superseded before acknowledgement")
        if source_version > paper.source_version:
            raise ValueError("Indexed version cannot exceed source version")
        paper.indexed_version = max(int(paper.indexed_version or 0), source_version)
        paper.indexed_at = datetime.now(timezone.utc)
        paper.last_index_error = None
        paper.index_claim_token = None
        paper.index_lease_expires_at = None
        paper.next_index_retry_at = None
        paper.index_status = (
            PaperIndexStatus.INDEXED.value
            if paper.indexed_version == paper.source_version
            else PaperIndexStatus.PENDING.value
        )
        self.session.flush()

    def mark_index_failed(
        self,
        paper: Paper,
        *,
        error: Exception | str,
        max_attempts: int,
        next_retry_at: Optional[datetime],
        claim_token: str,
    ) -> None:
        if paper.index_claim_token != claim_token:
            raise StaleIndexClaimError("Index claim was superseded before failure recording")
        sanitized_error = " ".join(str(error).split())[:500]
        exhausted = int(paper.index_attempts or 0) >= max_attempts
        paper.index_status = (
            PaperIndexStatus.DEAD_LETTER.value
            if exhausted
            else PaperIndexStatus.RETRY_PENDING.value
        )
        paper.last_index_error = sanitized_error
        paper.index_claim_token = None
        paper.index_lease_expires_at = None
        paper.next_index_retry_at = None if exhausted else next_retry_at
        self.session.flush()
