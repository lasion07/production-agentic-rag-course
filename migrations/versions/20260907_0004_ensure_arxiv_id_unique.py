"""Ensure adopted legacy schemas retain arxiv_id uniqueness.

Revision ID: 20260907_0004
Revises: 20260907_0003
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0004"
down_revision: Union[str, None] = "20260907_0003"
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


def downgrade() -> None:
    # Preserve data integrity during application rollback. The prior revision
    # supports both the legacy unique index and this equivalent constraint.
    pass
