"""Integration tests for the hybrid retriever against the real test database.

Scores are RRF fusion scores (sums of reciprocal ranks), not cosine
similarities — see ``app/retrieval/rrf.py``.
"""

import pytest

from app.core.config import settings
from app.retrieval.retriever import PgVectorRetriever
from tests.retrieval.conftest import (
    EXACT_CONTENT,
    HIDDEN_CONTENT,
    RND_CONTENT,
    embed_by_slot,
)

pytestmark = pytest.mark.integration

RRF_K = settings.rrf_k


async def test_semantic_match_outranks_orthogonal_chunks(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"iPhone revenue drivers": 0}), top_k=2
    )

    passages = await retriever.search("iPhone revenue drivers")

    assert passages[0].chunk_id == str(seeded_corpus["iphone"].id)
    # 'iPhone revenue drivers' has no full-text hit (no chunk carries all
    # three stemmed terms), so scores come from the semantic leg alone:
    # rank 1 contributes exactly 1/(k+1).
    assert passages[0].score == pytest.approx(1 / (RRF_K + 1))
    # the runner-up is one of the zero-cosine chunks — exact tie order is
    # unspecified in Postgres
    assert passages[1].chunk_id in {
        str(seeded_corpus["rnd"].id),
        str(seeded_corpus["exact"].id),
    }


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


async def test_keyword_query_semantic_miss_is_hit_by_fulltext_leg(
    db_session, seeded_corpus,
):
    """Issue 06 regression: keyword-style query, semantic leg blind to it.

    The query embeds to slot 1 (the R&D direction), which is orthogonal to
    the exact-term chunk (slot 4, cosine 0). With top_k=1 a semantic-only
    retriever would return the R&D chunk and drop the match entirely; the
    full-text leg ranks the exact identifier first and RRF fusion keeps it
    on top.
    """
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"agreement No. 0098765432": 1}), top_k=1
    )

    passages = await retriever.search("agreement No. 0098765432")

    assert [p.chunk_id for p in passages] == [str(seeded_corpus["exact"].id)]
    assert passages[0].content == EXACT_CONTENT
    # present in both legs: the fused score exceeds any single-leg
    # contribution of 1/(k+1)
    assert passages[0].score > 1 / (RRF_K + 1)


async def test_both_legs_agreeing_ranks_chunk_first(db_session, seeded_corpus):
    # Slot 0 is the iPhone direction and its content carries 'iPhone':
    # semantic rank 1 + full-text rank 1.
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"iPhone brands": 0}), top_k=8
    )

    passages = await retriever.search("iPhone brands")

    assert passages[0].chunk_id == str(seeded_corpus["iphone"].id)
    assert passages[0].score == pytest.approx(2 / (RRF_K + 1))


async def test_soft_deleted_documents_are_excluded(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"deleted probe": 2}), top_k=8
    )

    passages = await retriever.search("deleted probe")

    assert {p.chunk_id for p in passages} == {
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
        str(seeded_corpus["exact"].id),
    }
    assert HIDDEN_CONTENT not in {p.content for p in passages}


async def test_documents_of_non_corpus_owners_are_excluded(db_session, seeded_corpus):
    retriever = PgVectorRetriever(
        db_session, embed_by_slot({"foreign probe": 3}), top_k=8
    )

    passages = await retriever.search("foreign probe")

    assert {p.chunk_id for p in passages} == {
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
        str(seeded_corpus["exact"].id),
    }


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


# --- read_chunks (get_chunks) ------------------------------------------------


async def test_get_chunks_returns_neighbors_in_document_order(
    db_session, seeded_corpus
):
    retriever = PgVectorRetriever(db_session, embed_by_slot({}))

    passages = await retriever.get_chunks([str(seeded_corpus["rnd"].id)])

    # rnd is chunk_index 1; window 1 pulls in iphone (0) and unembedded (2)
    assert [p.chunk_id for p in passages] == [
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
        str(seeded_corpus["unembedded"].id),
    ]
    assert passages[1].content == RND_CONTENT


async def test_get_chunks_boundary_chunk_clips_window(db_session, seeded_corpus):
    retriever = PgVectorRetriever(db_session, embed_by_slot({}))

    passages = await retriever.get_chunks([str(seeded_corpus["iphone"].id)])

    # iphone is index 0: no left neighbor exists, window clips to 1 on the right
    assert [p.chunk_id for p in passages] == [
        str(seeded_corpus["iphone"].id),
        str(seeded_corpus["rnd"].id),
    ]


async def test_get_chunks_excludes_soft_deleted_and_foreign(db_session, seeded_corpus):
    retriever = PgVectorRetriever(db_session, embed_by_slot({}))

    passages = await retriever.get_chunks(
        [str(seeded_corpus["deleted"].id), str(seeded_corpus["foreign"].id)]
    )

    assert passages == []


async def test_get_chunks_zero_window_returns_only_targets(db_session, seeded_corpus):
    retriever = PgVectorRetriever(db_session, embed_by_slot({}))

    passages = await retriever.get_chunks(
        [str(seeded_corpus["iphone"].id)], neighbor_window=0
    )

    assert [p.chunk_id for p in passages] == [str(seeded_corpus["iphone"].id)]
    assert passages[0].content == seeded_corpus["iphone"].content
