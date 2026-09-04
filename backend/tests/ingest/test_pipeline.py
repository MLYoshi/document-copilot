import pytest
from sqlalchemy import select, text

from app.database.models import DocumentChunk, DocumentStatus, SourceDocument, User
from ingest.pipeline import ingest_corpus

pytestmark = pytest.mark.integration

AAPL_ACCESSION = "0000320193-24-000123"
NVDA_ACCESSION = "0001045810-25-000023"


async def test_ingest_seeds_corpus_owner_user(downloads_dir, session_factory, fake_embedder):
    stats = await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )

    assert stats.processed == 2
    async with session_factory() as session:
        user = await session.scalar(
            select(User).where(User.email == "corpus@system.local")
        )
        assert user is not None


async def test_documents_stored_with_completed_status_and_metadata(
    downloads_dir, session_factory, fake_embedder
):
    await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )

    async with session_factory() as session:
        docs = (await session.execute(select(SourceDocument))).scalars().all()
        assert len(docs) == 2
        by_accession = {d.metadata_json["accession_number"]: d for d in docs}

        doc = by_accession[AAPL_ACCESSION]
        owner = await session.scalar(
            select(User).where(User.email == "corpus@system.local")
        )
        assert doc.status is DocumentStatus.completed
        assert doc.user_id == owner.id
        assert doc.deleted_at is None
        assert doc.metadata_json["ticker"] == "AAPL"
        assert doc.metadata_json["form"] == "10-K"
        assert doc.source_url.startswith("https://www.sec.gov/")
        assert "Item 1. Business" in doc.content


async def test_chunks_have_embeddings_metadata_and_search_vector(
    downloads_dir, session_factory, fake_embedder
):
    await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )

    async with session_factory() as session:
        chunks = (
            (await session.execute(select(DocumentChunk))).scalars().all()
        )
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1024
            assert chunk.token_count > 0
            assert "section_path" in chunk.metadata_json
            assert chunk.chunk_index >= 0

        # full-text search is queryable at the SQL level via the generated column
        hits = (
            await session.execute(
                text(
                    "SELECT count(*) FROM document_chunks "
                    "WHERE search_vector @@ plainto_tsquery('english', 'smartphones')"
                )
            )
        ).scalar()
        assert hits >= 1


async def test_second_run_is_idempotent(downloads_dir, session_factory, fake_embedder):
    await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )
    async with session_factory() as session:
        doc_count = len((await session.execute(select(SourceDocument))).all())
        chunk_count = len((await session.execute(select(DocumentChunk))).all())

    stats = await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )

    assert stats.processed == 0
    assert stats.skipped == 2
    assert stats.failed == 0
    async with session_factory() as session:
        assert len((await session.execute(select(SourceDocument))).all()) == doc_count
        assert len((await session.execute(select(DocumentChunk))).all()) == chunk_count


async def test_missing_file_fails_single_filing_without_aborting_run(
    downloads_dir, session_factory, fake_embedder
):
    (downloads_dir / "2025" / "nvda_10k.html").unlink()

    stats = await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )

    assert stats.processed == 1
    assert stats.failed == 1
    assert stats.skipped == 0


async def test_failed_document_is_marked_failed_and_retried_on_rerun(
    downloads_dir, session_factory, fake_embedder
):
    fake_embedder.fail_on = "NVIDIA"

    first = await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )
    assert first.processed == 1
    assert first.failed == 1

    async with session_factory() as session:
        doc = await session.scalar(
            select(SourceDocument).where(
                SourceDocument.metadata_json["accession_number"].astext
                == NVDA_ACCESSION
            )
        )
        assert doc is not None
        assert doc.status is DocumentStatus.failed

    # rerun with a healthy embedder rebuilds only the failed document
    fake_embedder.fail_on = None
    second = await ingest_corpus(
        downloads_dir, session_factory=session_factory, embed=fake_embedder
    )
    assert second.processed == 1
    assert second.skipped == 1
    assert second.failed == 0

    async with session_factory() as session:
        doc = await session.scalar(
            select(SourceDocument).where(
                SourceDocument.metadata_json["accession_number"].astext
                == NVDA_ACCESSION
            )
        )
        assert doc.status is DocumentStatus.completed
        chunk_count = len(
            (
                await session.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                )
            ).all()
        )
        assert chunk_count > 0
