"""Use Supabase Auth and enable RLS on application tables.

Revision ID: e7a25c6d84f1
Revises: 3c7f1a9e4b52
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7a25c6d84f1"
down_revision: str | Sequence[str] | None = "3c7f1a9e4b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = (
    "chat_threads",
    "chat_messages",
    "message_citations",
    "source_documents",
    "document_chunks",
    "document_tables",
)


def upgrade() -> None:
    op.drop_table("refresh_tokens")
    for table in ("chat_threads", "source_documents"):
        op.drop_constraint(f"{table}_user_id_fkey", table, type_="foreignkey")
    op.drop_table("users")
    for table in ("chat_threads", "source_documents"):
        op.create_foreign_key(
            f"{table}_user_id_fkey",
            table,
            "users",
            ["user_id"],
            ["id"],
            source_schema="public",
            referent_schema="auth",
            ondelete="CASCADE",
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY chat_threads_owner ON public.chat_threads "
        "FOR ALL TO authenticated USING (user_id = auth.uid()) "
        "WITH CHECK (user_id = auth.uid())"
    )
    op.execute(
        "CREATE POLICY source_documents_read ON public.source_documents "
        "FOR SELECT TO authenticated USING (deleted_at IS NULL)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY chat_threads_owner ON public.chat_threads")
    op.execute("DROP POLICY source_documents_read ON public.source_documents")
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for table in ("chat_threads", "source_documents"):
        op.drop_constraint(f"{table}_user_id_fkey", table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_user_id_fkey",
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
