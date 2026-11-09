from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_drop_document_passages"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("document_passages")
    op.drop_index("source_documents_summary_search_idx", table_name="source_documents")
    op.drop_column("source_documents", "summary_search_vector")


def downgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column(
            "summary_search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', coalesce(summary, ''))", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "source_documents_summary_search_idx",
        "source_documents",
        ["summary_search_vector"],
        postgresql_using="gin",
    )
    op.create_table(
        "document_passages",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["source_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_passages_document_id"),
        "document_passages",
        ["document_id"],
    )
    op.create_index(
        "uq_document_passages_order",
        "document_passages",
        ["document_id", "passage_index"],
        unique=True,
    )
    op.execute("ALTER TABLE public.document_passages ENABLE ROW LEVEL SECURITY")
