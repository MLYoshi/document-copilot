"""Simplify schema for MVP: drop document_tables and message_citations,
fold citations into chat_messages, remove redundant column and index.

Revision ID: c8f14a2e9d06
Revises: e7a25c6d84f1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8f14a2e9d06"
down_revision: str | Sequence[str] | None = "e7a25c6d84f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_column("chat_messages", "ai_sdk_message")
    op.drop_index("document_chunks_metadata_idx", table_name="document_chunks")
    op.drop_column("document_chunks", "token_count")
    op.drop_table("message_citations")
    op.drop_table("document_tables")


def downgrade() -> None:
    op.create_table(
        "document_tables",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("table_index", sa.Integer(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_tables_document_id", "document_tables", ["document_id"])
    op.create_index("uq_document_tables_order", "document_tables", ["document_id", "table_index"], unique=True)
    op.execute("ALTER TABLE public.document_tables ENABLE ROW LEVEL SECURITY")
    op.create_table(
        "message_citations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_citations_chunk_id", "message_citations", ["chunk_id"])
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])
    op.execute("ALTER TABLE public.message_citations ENABLE ROW LEVEL SECURITY")
    op.add_column("document_chunks", sa.Column("token_count", sa.Integer(), nullable=True))
    op.create_index(
        "document_chunks_metadata_idx",
        "document_chunks",
        ["metadata_json"],
        postgresql_using="gin",
    )
    op.add_column(
        "chat_messages",
        sa.Column("ai_sdk_message", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_column("chat_messages", "citations")
