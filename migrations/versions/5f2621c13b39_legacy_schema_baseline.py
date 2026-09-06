"""Record the legacy 17-column papers schema as the adoption baseline.

Revision ID: 5f2621c13b39
Revises:
Create Date: 2025-05-01

This revision intentionally performs no DDL. Existing course databases already
carry this revision identifier. Fresh databases continue to the next revision,
which creates the complete table when it is absent.
"""

from typing import Sequence, Union

revision: str = "5f2621c13b39"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
