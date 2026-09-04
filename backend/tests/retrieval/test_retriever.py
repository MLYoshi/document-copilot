"""Integration tests for PgVectorRetriever against the real test database."""

import pytest

from app.retrieval.retriever import PgVectorRetriever
from tests.retrieval.conftest import HIDDEN_CONTENT, RND_CONTENT, embed_by_slot

pytestmark = pytest.mark.integration


async def test_orders_by_similarity_and_respects_top_k(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"iPhone revenue drivers": 0}), top_k=2
    )

    passages = await retriever.search("iPhone revenue drivers")

    assert [p.chunk_id for p in passages] == [
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
    ]
    # same slot -> identical direction -> perfect cosine; the orthogonal
    # filler chunk scores 0.0
    assert passages[0].score == pytest.approx(1.0)
    assert passages[1].score == pytest.approx(0.0)
    assert passages[0].score >= passages[1].score


async def test_passages_carry_document_and_chunk_metadata(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"R&D spending": 1}), top_k=1
    )

    passages = await retriever.search("R&D spending")

    assert len(passages) == 1
    passage = passages[0]
    assert passage.chunk_id == str(seeded_corpus["rnd"].id)
    assert passage.document_id == str(seeded_corpus["rnd"].document_id)
    assert passage.chunk_index == 1
    assert passage.content == RND_CONTENT
    assert passage.section_path == "Item 1. Business > Research and Development"
    assert passage.title == "Apple Inc. Form 10-K 2024"
    assert passage.ticker == "AAPL"
    assert passage.form == "10-K"
    assert passage.filing_date == "2024-11-01"
    assert (
        passage.source_url == "https://www.sec.gov/Archives/edgar/data/320193/aapl.htm"
    )


async def test_soft_deleted_documents_are_excluded(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"deleted probe": 2}), top_k=8
    )

    passages = await retriever.search("deleted probe")

    assert [p.chunk_id for p in passages] == [
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
    ]
    assert HIDDEN_CONTENT not in {p.content for p in passages}


async def test_documents_of_non_corpus_owners_are_excluded(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"foreign probe": 3}), top_k=8
    )

    passages = await retriever.search("foreign probe")

    assert [p.chunk_id for p in passages] == [
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
    ]


async def test_chunks_without_embedding_are_excluded(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"unembedded probe": 2}), top_k=8
    )

    passages = await retriever.search("unembedded probe")

    assert str(seeded_corpus["unembedded"].id) not in {p.chunk_id for p in passages}


async def test_empty_corpus_returns_empty_list(db_session, fake_embedder):
    # db_engine truncates every table, so no seed fixture -> empty corpus
    retriever = PgVectorRetriever(db_session, fake_embedder, top_k=8)

    assert await retriever.search("anything at all") == []


async def test_retriever_embeds_the_user_query(db_session, seeded_corpus):
    embed = embed_by_slot({"raw question text": 0})
    retriever = PgVectorRetriever(db_session, embed, top_k=1)

    await retriever.search("raw question text")

    assert embed.calls == ["raw question text"]
