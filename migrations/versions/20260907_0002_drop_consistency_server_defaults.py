"""Remove temporary consistency-state backfill defaults.

Revision ID: 20260907_0002
Revises: 20260906_0001
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0002"
down_revision: Union[str, None] = "20260906_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = {
    "source_version": "1",
    "indexed_version": "0",
    "index_status": "pending",
    "index_attempts": "0",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "papers" not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns("papers")}
    for name in COLUMNS:
        if name in existing:
            op.alter_column("papers", name, server_default=None)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "papers" not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_columns("papers")}
    for name, default in COLUMNS.items():
        if name in existing:
            op.alter_column("papers", name, server_default=default)
