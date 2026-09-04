"""widen document_chunks.embedding to 2048 dimensions

Revision ID: b3f1c8d47a29
Revises: d9939f390cd5
Create Date: 2026-09-04 12:00:00.000000

Switches embeddings from OpenAI text-embedding-3-small (1536-dim) to the
OpenRouter-hosted nvidia/nemotron-3-embed-1b:free, whose native width is
2048 and which rejects any `dimensions` override.

Old 1536-dim vectors cannot be cast to vector(2048), so they are dropped and
their documents reset to `pending` — the next ingest run rebuilds them.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3f1c8d47a29'
down_revision: Union[str, Sequence[str], None] = 'd9939f390cd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector forbids altering a column's type while an HNSW index covers it
    op.drop_index(
        'document_chunks_embedding_idx',
        table_name='document_chunks',
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.execute(sa.text("UPDATE document_chunks SET embedding = NULL"))
    op.execute(sa.text("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(2048)"))
    op.execute(sa.text("""
        UPDATE source_documents SET status = 'pending'
        WHERE id IN (SELECT document_id FROM document_chunks)
    """))
    op.create_index(
        'document_chunks_embedding_idx',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    op.drop_index(
        'document_chunks_embedding_idx',
        table_name='document_chunks',
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.execute(sa.text("UPDATE document_chunks SET embedding = NULL"))
    op.execute(sa.text("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)"))
    op.execute(sa.text("""
        UPDATE source_documents SET status = 'pending'
        WHERE id IN (SELECT document_id FROM document_chunks)
    """))
    op.create_index(
        'document_chunks_embedding_idx',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
