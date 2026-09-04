"""narrow document_chunks.embedding to 1024 dimensions

Revision ID: 29baa7ace0d1
Revises: d9939f390cd5
Create Date: 2026-09-04 16:14:43.089070

Switches embeddings to liquid/lfm-2.5-embedding-350m:free, whose native width
is 1024. pgvector refuses to build an HNSW (or IVFFlat) index over vectors
wider than 2000 dimensions, so the column width must stay under that cap.

pgvector cannot cast between vector widths, so existing vectors are dropped and
their documents reset to `pending` — the next ingest run rebuilds them.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '29baa7ace0d1'
down_revision: Union[str, Sequence[str], None] = 'd9939f390cd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = 'document_chunks_embedding_idx'


def _drop_index() -> None:
    # pgvector forbids altering a column's type while an HNSW index covers it
    op.drop_index(
        _INDEX,
        table_name='document_chunks',
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def _create_index() -> None:
    op.create_index(
        _INDEX,
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def _retype(width: int) -> None:
    op.execute(sa.text("UPDATE document_chunks SET embedding = NULL"))
    op.execute(
        sa.text(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({width})")
    )
    op.execute(
        sa.text("""
            UPDATE source_documents SET status = 'pending'
            WHERE id IN (SELECT document_id FROM document_chunks)
        """)
    )


def upgrade() -> None:
    _drop_index()
    _retype(1024)
    _create_index()


def downgrade() -> None:
    _drop_index()
    _retype(1536)
    _create_index()
