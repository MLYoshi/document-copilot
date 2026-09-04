"""Fast tests for the chunk-embed-load stage: fake session + fake embedder.

``FakeSession`` scripts the per-document chunk counts that drive the
idempotency skip; the root conftest's ``FakeEmbedder`` stands in for the
OpenRouter client. No database, no network.
"""

from uuid import uuid4

from app.database.models import DocumentChunk, DocumentStatus, SourceDocument
from ingest.embeddings import embed_corpus

CONTENT = (
    "## Item 1. Business\n\nApple designs smartphones and personal computers.\n\n"
    "## Item 1A. Risk Factors\n\nSupply chain disruptions may affect product availability."
)


def _document(content: str = CONTENT, status: DocumentStatus = DocumentStatus.completed):
    return SourceDocument(
        id=uuid4(),
        user_id=uuid4(),
        content=content,
        status=status,
        metadata_json={"accession_number": "0000320193-24-000123"},
    )


async def test_completed_document_is_chunked_and_embedded(fake_session, fake_embedder):
    document = _document()
    fake_session.queue([document], 0)  # select docs, then chunk count 0

    stats = await embed_corpus(
        session_factory=lambda: fake_session, embed=fake_embedder
    )

    assert stats == {"processed": 1, "skipped": 0, "failed": 0}
    chunks = [o for o in fake_session.added if isinstance(o, DocumentChunk)]
    assert len(chunks) > 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.document_id == document.id
        assert chunk.token_count > 0
        assert "section_path" in chunk.metadata_json
        assert len(chunk.embedding) == 1024
    # one embed call with all chunk contents, one commit
    assert fake_embedder.batches == [[c.content for c in chunks]]
    assert fake_session.commits == 1


async def test_document_with_existing_chunks_is_skipped(fake_session, fake_embedder):
    fake_session.queue([_document()], 3)  # already carries chunks

    stats = await embed_corpus(
        session_factory=lambda: fake_session, embed=fake_embedder
    )

    assert stats == {"processed": 0, "skipped": 1, "failed": 0}
    assert fake_session.added == []
    assert fake_embedder.batches == []


async def test_every_completed_document_is_embedded_in_one_run(fake_session, fake_embedder):
    docs = [_document(), _document(content="## Item 7\n\nDiscussion and analysis.")]
    fake_session.queue(docs, 0, 0)

    stats = await embed_corpus(
        session_factory=lambda: fake_session, embed=fake_embedder
    )

    assert stats == {"processed": 2, "skipped": 0, "failed": 0}
    chunks = [o for o in fake_session.added if isinstance(o, DocumentChunk)]
    assert {c.document_id for c in chunks} == {d.id for d in docs}
    # chunk_index restarts per document
    by_doc = {d.id: sorted(c.chunk_index for c in chunks if c.document_id == d.id) for d in docs}
    assert all(indices == list(range(len(indices))) for indices in by_doc.values())


async def test_embedding_failure_is_counted_and_rolled_back(fake_session, fake_embedder):
    fake_embedder.fail_on = "smartphones"
    fake_session.queue([_document()], 0)

    stats = await embed_corpus(
        session_factory=lambda: fake_session, embed=fake_embedder
    )

    assert stats == {"processed": 0, "skipped": 0, "failed": 1}
    assert fake_session.rollbacks == 1
    assert fake_session.commits == 0
    assert not any(isinstance(o, DocumentChunk) for o in fake_session.added)


async def test_document_without_chunks_fails(fake_session, fake_embedder):
    fake_session.queue([_document(content="")], 0)

    stats = await embed_corpus(
        session_factory=lambda: fake_session, embed=fake_embedder
    )

    assert stats == {"processed": 0, "skipped": 0, "failed": 1}
    assert fake_session.rollbacks == 1
    assert fake_embedder.batches == []
