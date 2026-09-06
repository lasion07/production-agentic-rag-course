"""Drop the redundant arxiv_id unique index.

Revision ID: 20260907_0003
Revises: 20260907_0002
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0003"
down_revision: Union[str, None] = "20260907_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "papers" not in inspector.get_table_names():
        return
    unique_constraints = inspector.get_unique_constraints("papers")
    has_arxiv_unique = any(
        set(item.get("column_names") or []) == {"arxiv_id"}
        for item in unique_constraints
    )
    if not has_arxiv_unique:
        op.create_unique_constraint("uq_papers_arxiv_id", "papers", ["arxiv_id"])
        inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("papers")}
    if "ix_papers_arxiv_id" in indexes:
        op.drop_index("ix_papers_arxiv_id", table_name="papers")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "papers" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("papers")}
    if "ix_papers_arxiv_id" not in indexes:
        op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"], unique=True)
