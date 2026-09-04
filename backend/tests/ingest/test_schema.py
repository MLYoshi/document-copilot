"""Guards for the one invariant pgvector cannot enforce on its own.

The embedding column width lives in three places: the migration that created it,
the ORM model, and ``settings.embedding_dimensions``. pgvector will not cast
between widths, so if they drift the failure only surfaces as a SQL error on the
first real write — after the embeddings have already been paid for.
"""

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.database.models import DocumentChunk


def test_orm_embedding_width_tracks_settings():
    # guards against the width being hardcoded back into the model
    assert DocumentChunk.__table__.c.embedding.type.dim == settings.embedding_dimensions


@pytest.mark.integration
async def test_migrated_column_width_tracks_settings(db_session):
    # migrations cannot import settings, so check the live catalog instead of
    # the revision files — this is what catches a retype that was never applied
    column_type = (
        await db_session.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = 'document_chunks'::regclass "
                "AND a.attname = 'embedding'"
            )
        )
    ).scalar()

    assert column_type == f"vector({settings.embedding_dimensions})"
