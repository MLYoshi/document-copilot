"""initial: pgvector extension

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("create extension if not exists vector")


def downgrade() -> None:
    op.execute("drop extension if exists vector")
