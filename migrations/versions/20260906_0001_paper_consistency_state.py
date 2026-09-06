"""Create papers schema and add durable index consistency state.

Revision ID: 20260906_0001
Revises: 5f2621c13b39
Create Date: 2026-09-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0001"
down_revision: Union[str, None] = "5f2621c13b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSISTENCY_COLUMNS = (
    "source_version",
    "indexed_version",
    "index_status",
    "index_attempts",
    "index_claim_token",
    "last_index_attempt_at",
    "index_lease_expires_at",
    "next_index_retry_at",
    "indexed_at",
    "last_index_error",
)


def _create_papers_table() -> None:
    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arxiv_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("published_date", sa.DateTime(), nullable=False),
        sa.Column("pdf_url", sa.String(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("parser_used", sa.String(), nullable=True),
        sa.Column("parser_metadata", sa.JSON(), nullable=True),
        sa.Column("pdf_processed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("pdf_processing_date", sa.DateTime(), nullable=True),
        sa.Column("source_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("indexed_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("index_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_claim_token", sa.String(length=36), nullable=True),
        sa.Column("last_index_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_index_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_index_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("source_version >= 1", name="ck_papers_source_version_positive"),
        sa.CheckConstraint("indexed_version >= 0", name="ck_papers_indexed_version_nonnegative"),
        sa.CheckConstraint("indexed_version <= source_version", name="ck_papers_index_version_order"),
        sa.CheckConstraint("index_attempts >= 0", name="ck_papers_index_attempts_nonnegative"),
        sa.CheckConstraint(
            "index_status IN ('pending', 'indexing', 'retry_pending', 'indexed', 'dead_letter')",
            name="ck_papers_index_status_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("arxiv_id"),
    )
    op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"], unique=True)
    op.create_index(
        "ix_papers_index_reconciliation",
        "papers",
        ["index_status", "next_index_retry_at"],
        unique=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "papers" not in inspector.get_table_names():
        _create_papers_table()
        return

    existing_columns = {item["name"] for item in inspector.get_columns("papers")}
    additions = {
        "source_version": sa.Column("source_version", sa.Integer(), server_default="1", nullable=False),
        "indexed_version": sa.Column("indexed_version", sa.Integer(), server_default="0", nullable=False),
        "index_status": sa.Column("index_status", sa.String(32), server_default="pending", nullable=False),
        "index_attempts": sa.Column("index_attempts", sa.Integer(), server_default="0", nullable=False),
        "index_claim_token": sa.Column("index_claim_token", sa.String(36), nullable=True),
        "last_index_attempt_at": sa.Column("last_index_attempt_at", sa.DateTime(timezone=True), nullable=True),
        "index_lease_expires_at": sa.Column("index_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        "next_index_retry_at": sa.Column("next_index_retry_at", sa.DateTime(timezone=True), nullable=True),
        "indexed_at": sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        "last_index_error": sa.Column("last_index_error", sa.Text(), nullable=True),
    }
    for name, column in additions.items():
        if name not in existing_columns:
            op.add_column("papers", column)

    inspector = sa.inspect(bind)
    checks = {item["name"] for item in inspector.get_check_constraints("papers")}
    constraints = {
        "ck_papers_source_version_positive": "source_version >= 1",
        "ck_papers_indexed_version_nonnegative": "indexed_version >= 0",
        "ck_papers_index_version_order": "indexed_version <= source_version",
        "ck_papers_index_attempts_nonnegative": "index_attempts >= 0",
        "ck_papers_index_status_valid": (
            "index_status IN ('pending', 'indexing', 'retry_pending', 'indexed', 'dead_letter')"
        ),
    }
    for name, condition in constraints.items():
        if name not in checks:
            op.create_check_constraint(name, "papers", condition)

    indexes = {item["name"] for item in inspector.get_indexes("papers")}
    if "ix_papers_index_reconciliation" not in indexes:
        op.create_index(
            "ix_papers_index_reconciliation",
            "papers",
            ["index_status", "next_index_retry_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "papers" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("papers")}
    if "ix_papers_index_reconciliation" in indexes:
        op.drop_index("ix_papers_index_reconciliation", table_name="papers")
    checks = {item["name"] for item in inspector.get_check_constraints("papers")}
    for name in (
        "ck_papers_source_version_positive",
        "ck_papers_indexed_version_nonnegative",
        "ck_papers_index_version_order",
        "ck_papers_index_attempts_nonnegative",
        "ck_papers_index_status_valid",
    ):
        if name in checks:
            op.drop_constraint(name, "papers", type_="check")
    existing_columns = {item["name"] for item in inspector.get_columns("papers")}
    for name in reversed(CONSISTENCY_COLUMNS):
        if name in existing_columns:
            op.drop_column("papers", name)
