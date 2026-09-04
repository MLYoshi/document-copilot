"""narrow document_chunks.embedding to 1024 dimensions

Revision ID: 29baa7ace0d1
Revises: d9939f390cd5
Create Date: 2026-09-04 16:14:43.089070

Switches embeddings to baai/bge-m3, whose native width is 1024. pgvector
refuses to build an HNSW (or IVFFlat) index over vectors wider than 2000
dimensions, so the column width must stay under that cap.

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

# Literals on purpose: a migration is a snapshot of the schema at its point in
# history, so it must not import the ORM model — whose width tracks
# settings.embedding_dimensions. _WIDTH_AFTER has to equal that setting;
# tests/ingest/test_schema.py fails when the two drift apart.
_WIDTH_BEFORE = 1536  # as created by 79bac489581f
_WIDTH_AFTER = 1024   # keep in sync with settings.embedding_dimensions


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
    _retype(_WIDTH_AFTER)
    _create_index()


def downgrade() -> None:
    # Restores the width 79bac489581f created, and is only meaningful as a step
    # towards an older checkout: the ORM model sits at _WIDTH_AFTER, so the
    # current application cannot write to the downgraded column. Run
    # `alembic upgrade head` again before starting the server.
    _drop_index()
    _retype(_WIDTH_BEFORE)
    _create_index()
