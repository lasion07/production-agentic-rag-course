import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from src.db.interfaces.postgresql import Base


class PaperIndexStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    RETRY_PENDING = "retry_pending"
    INDEXED = "indexed"
    DEAD_LETTER = "dead_letter"


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        CheckConstraint("source_version >= 1", name="ck_papers_source_version_positive"),
        CheckConstraint("indexed_version >= 0", name="ck_papers_indexed_version_nonnegative"),
        CheckConstraint("indexed_version <= source_version", name="ck_papers_index_version_order"),
        CheckConstraint("index_attempts >= 0", name="ck_papers_index_attempts_nonnegative"),
        CheckConstraint(
            "index_status IN ('pending', 'indexing', 'retry_pending', 'indexed', 'dead_letter')",
            name="ck_papers_index_status_valid",
        ),
        Index("ix_papers_index_reconciliation", "index_status", "next_index_retry_at"),
    )

    # Core arXiv metadata
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    arxiv_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    authors = Column(JSON, nullable=False)
    abstract = Column(Text, nullable=False)
    categories = Column(JSON, nullable=False)
    published_date = Column(DateTime, nullable=False)
    pdf_url = Column(String, nullable=False)

    # Parsed PDF content (added for comprehensive storage)
    raw_text = Column(Text, nullable=True)
    sections = Column(JSON, nullable=True)
    references = Column(JSON, nullable=True)

    # PDF processing metadata
    parser_used = Column(String, nullable=True)
    parser_metadata = Column(JSON, nullable=True)
    pdf_processed = Column(Boolean, default=False, nullable=False)
    pdf_processing_date = Column(DateTime, nullable=True)

    # PostgreSQL is the source of truth for search-index consistency.
    source_version = Column(Integer, default=1, nullable=False)
    indexed_version = Column(Integer, default=0, nullable=False)
    index_status = Column(String(32), default=PaperIndexStatus.PENDING.value, nullable=False)
    index_attempts = Column(Integer, default=0, nullable=False)
    index_claim_token = Column(String(36), nullable=True)
    last_index_attempt_at = Column(DateTime(timezone=True), nullable=True)
    index_lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    next_index_retry_at = Column(DateTime(timezone=True), nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    last_index_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
