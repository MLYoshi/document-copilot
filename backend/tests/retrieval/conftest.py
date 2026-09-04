"""Corpus seeding for retriever tests.

Vectors are seeded directly on the ORM models so each chunk's direction is
under test control: one-hot vectors on disjoint slots are mutually orthogonal,
giving exact cosine scores (1.0 same slot, 0.0 across slots) without needing
a real embedding model.
"""

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.database.models import DocumentChunk, DocumentStatus, SourceDocument, User

DIMS = settings.embedding_dimensions

iPhone_CONTENT = (
    "Apple Inc. designs and sells smartphones, personal computers and "
    "wearables under the iPhone, Mac and Watch brands."
)
RND_CONTENT = "Investment in research and development grew to fund new silicon."
HIDDEN_CONTENT = "This chunk belongs to a deleted document and must stay hidden."
# Carries an exact identifier that keyword queries match but semantic
# retrieval cannot: its vector is orthogonal to every other test query.
EXACT_CONTENT = (
    "The aggregate purchase price was $1,234,567,890 recorded under "
    "agreement No. 0098765432 with the underwriters."
)


def slot_vector(slot: int) -> list[float]:
    vec = [0.0] * DIMS
    vec[slot] = 1.0
    return vec


def embed_by_slot(slot_by_query: dict[str, int]):
    """Deterministic EmbedFn: each known query maps to its slot's unit vector."""
    calls: list[str] = []

    async def embed(texts: list[str]) -> list[list[float]]:
        calls.extend(texts)
        return [slot_vector(slot_by_query[t]) for t in texts]

    embed.calls = calls  # type: ignore[attr-defined]
    return embed


@pytest.fixture
async def seeded_corpus(db_session):
    """Corpus with one live, one soft-deleted and one foreign-user document."""
    owner = User(email=settings.corpus_owner_email, password_hash="x" * 60)
    other = User(email="analyst@example.com", password_hash="x" * 60)
    db_session.add_all([owner, other])
    await db_session.flush()

    live_doc = SourceDocument(
        user_id=owner.id,
        title="Apple Inc. Form 10-K 2024",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/aapl.htm",
        metadata_json={
            "ticker": "AAPL",
            "form": "10-K",
            "filing_date": "2024-11-01",
            "accession_number": "0000320193-24-000123",
        },
        content="Apple 10-K body",
        status=DocumentStatus.completed,
    )
    deleted_doc = SourceDocument(
        user_id=owner.id,
        title="Deleted Filing",
        metadata_json={"ticker": "AAPL", "form": "10-K"},
        content="deleted body",
        status=DocumentStatus.completed,
        deleted_at=datetime.now(UTC),
    )
    foreign_doc = SourceDocument(
        user_id=other.id,
        title="Analyst Upload",
        metadata_json={"ticker": "TSLA", "form": "10-K"},
        content="foreign body",
        status=DocumentStatus.completed,
    )
    db_session.add_all([live_doc, deleted_doc, foreign_doc])
    await db_session.flush()

    chunk_iphone = DocumentChunk(
        document_id=live_doc.id,
        chunk_index=0,
        content=iPhone_CONTENT,
        token_count=20,
        metadata_json={"section_path": "Item 1. Business"},
        embedding=slot_vector(0),
    )
    chunk_rnd = DocumentChunk(
        document_id=live_doc.id,
        chunk_index=1,
        content=RND_CONTENT,
        token_count=12,
        metadata_json={"section_path": "Item 1. Business > Research and Development"},
        embedding=slot_vector(1),
    )
    chunk_unembedded = DocumentChunk(
        document_id=live_doc.id,
        chunk_index=2,
        content="Awaiting embedding backfill.",
        token_count=5,
        metadata_json={"section_path": "Item 7. MD&A"},
        embedding=None,
    )
    chunk_deleted = DocumentChunk(
        document_id=deleted_doc.id,
        chunk_index=0,
        content=HIDDEN_CONTENT,
        token_count=12,
        metadata_json={"section_path": "Item 1. Business"},
        embedding=slot_vector(2),
    )
    chunk_foreign = DocumentChunk(
        document_id=foreign_doc.id,
        chunk_index=0,
        content="Foreign corpus chunk.",
        token_count=5,
        metadata_json={"section_path": "Item 1. Business"},
        embedding=slot_vector(3),
    )
    chunk_exact = DocumentChunk(
        document_id=live_doc.id,
        chunk_index=3,
        content=EXACT_CONTENT,
        token_count=20,
        metadata_json={"section_path": "Item 7. MD&A > Acquisitions"},
        embedding=slot_vector(4),
    )
    db_session.add_all(
        [
            chunk_iphone,
            chunk_rnd,
            chunk_unembedded,
            chunk_deleted,
            chunk_foreign,
            chunk_exact,
        ]
    )
    await db_session.commit()

    return {
        "iphone": chunk_iphone,
        "rnd": chunk_rnd,
        "unembedded": chunk_unembedded,
        "deleted": chunk_deleted,
        "foreign": chunk_foreign,
        "exact": chunk_exact,
    }
