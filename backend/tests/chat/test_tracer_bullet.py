"""End-to-end tracer bullet with real OpenRouter credentials.

Real embeddings ingest the fixture corpus (2 filings, ~a dozen chunks), then a
real chat model answers through the full orchestrator. Costs a few cents of
free-tier quota at most, so it is skipped without an API key like the ingest
smoke test.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.chat.orchestrator import answer_question
from app.core.config import settings
from app.core.embeddings import get_embedding
from app.database.models import DocumentChunk
from app.retrieval.retriever import PgVectorRetriever
from ingest.pipeline import ingest_corpus

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.openrouter_api_key,
        reason="OPENROUTER_API_KEY not set: the live embedding and chat calls cost money",
    ),
]

IN_CORPUS_QUESTION = (
    "According to the passages, what drove NVIDIA's Data Center revenue growth "
    "in fiscal year 2025?"
)
OUT_OF_CORPUS_QUESTION = "How many 737 MAX aircraft did Boeing deliver in 2024?"


async def test_corpus_question_returns_citations_inside_the_retrieval_set(
    db_session, session_factory, downloads_dir
):
    stats = await ingest_corpus(downloads_dir, session_factory=session_factory)
    assert stats.processed == 2

    result = await answer_question(
        db_session,
        user_id=uuid4(),
        thread_id=uuid4(),
        question=IN_CORPUS_QUESTION,
    )

    assert result.evidence_sufficient is True
    assert result.citations

    # re-derive the retrieval set independently: every citation must land in it
    retriever = PgVectorRetriever(db_session, get_embedding)
    retrieval_set = await retriever.search(IN_CORPUS_QUESTION)
    retrieved_by_id = {p.chunk_id: p for p in retrieval_set}

    for citation in result.citations:
        assert citation.chunk_id in retrieved_by_id
        passage = next(
            p for p in result.cited_passages if p.chunk_id == citation.chunk_id
        )
        assert " ".join(citation.quote.split()) in " ".join(passage.content.split())

    # cited_passages are the exact DB rows, not model-invented text
    cited_ids = {c.chunk_id for c in result.citations}
    rows = (
        (
            await db_session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.id.in_([UUID(c) for c in cited_ids])
                )
            )
        )
        .scalars()
        .all()
    )
    assert {str(r.id): r.content for r in rows} == {
        p.chunk_id: p.content for p in result.cited_passages
    }


async def test_out_of_corpus_question_declares_insufficient_evidence(
    db_session, session_factory, downloads_dir
):
    await ingest_corpus(downloads_dir, session_factory=session_factory)

    result = await answer_question(
        db_session,
        user_id=uuid4(),
        thread_id=uuid4(),
        question=OUT_OF_CORPUS_QUESTION,
    )

    assert result.evidence_sufficient is False
