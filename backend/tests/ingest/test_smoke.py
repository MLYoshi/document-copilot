"""Live end-to-end check of the paid path: OpenRouter -> pgvector -> back.

Skipped without an API key — unlike the rest of the ingest suite this one spends
real money, so it must never be the reason a keyless checkout goes red.
"""
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.database.models import SourceDocument
from ingest.smoke import SMOKE_ACCESSION, run_smoke

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.openrouter_api_key,
        reason="OPENROUTER_API_KEY not set: the live embedding call costs money",
    ),
]


async def test_smoke_round_trip_leaves_no_rows_behind(
    downloads_dir, session_factory, db_session
):
    report = await run_smoke(downloads_dir, session_factory=session_factory)

    assert report.chunks_written > 0
    assert report.dimensions == settings.embedding_dimensions

    # the smoke document must not linger in the corpus, or the next full ingest
    # would trip over a filing that is not in the manifest
    leftovers = (
        (
            await db_session.execute(
                select(SourceDocument).where(
                    SourceDocument.metadata_json["accession_number"].astext
                    == SMOKE_ACCESSION
                )
            )
        )
        .scalars()
        .all()
    )
    assert leftovers == []
