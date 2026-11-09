from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WIDTH = settings.embedding_dimensions

RLS_TABLES = (
    "chat_threads",
    "chat_messages",
    "source_documents",
    "document_passages",
)


def upgrade() -> None:
    op.execute("create extension if not exists vector")

    document_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        name="document_status",
        create_type=False,
    )
    document_status.create(op.get_bind(), checkfirst=True)
    message_role = postgresql.ENUM(
        "user",
        "assistant",
        name="message_role",
        create_type=False,
    )
    message_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "chat_threads",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_threads_user_id"), "chat_threads", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_thread_id"), "chat_messages", ["thread_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_embedding", VECTOR(dim=_WIDTH), nullable=True),
        sa.Column(
            "summary_search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(summary, ''))", persisted=True),
            nullable=False,
        ),
        sa.Column("status", document_status, server_default="pending", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_source_documents_user_id"), "source_documents", ["user_id"])
    op.create_index(op.f("ix_source_documents_status"), "source_documents", ["status"])
    op.create_index(op.f("ix_source_documents_deleted_at"), "source_documents", ["deleted_at"])
    op.create_index(
        "source_documents_summary_embedding_idx",
        "source_documents",
        ["summary_embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"summary_embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "source_documents_summary_search_idx",
        "source_documents",
        ["summary_search_vector"],
        postgresql_using="gin",
    )

    op.create_table(
        "document_passages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_passages_document_id"), "document_passages", ["document_id"])
    op.create_index(
        "uq_document_passages_order",
        "document_passages",
        ["document_id", "passage_index"],
        unique=True,
    )

    for table in RLS_TABLES:
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
    op.execute("DROP POLICY source_documents_read ON public.source_documents")
    op.execute("DROP POLICY chat_threads_owner ON public.chat_threads")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("document_passages")
    op.drop_table("source_documents")
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")

    postgresql.ENUM("pending", "processing", "completed", "failed", name="document_status").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM("user", "assistant", name="message_role").drop(op.get_bind(), checkfirst=True)
    op.execute("drop extension if exists vector")
