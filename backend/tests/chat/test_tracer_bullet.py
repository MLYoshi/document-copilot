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
from app.database.models import DocumentChunk, SourceDocument, User
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

    # The agent loop retrieves through its own tool calls (possibly with a
    # reformulated query, possibly reading neighbor chunks), so the retrieval
    # set is whatever the tools accumulated — replaying search(question)
    # independently no longer reproduces it. The enforceable invariant is
    # weaker and still meaningful: every citation points at a real chunk of
    # the corpus owner's filings, with verbatim-matching text.
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
    assert rows, "citations must resolve to real corpus chunks"
    owner_chunk_ids = set(
        (
            await db_session.execute(
                select(DocumentChunk.id)
                .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
                .join(User, SourceDocument.user_id == User.id)
                .where(
                    DocumentChunk.id.in_([UUID(c) for c in cited_ids]),
                    User.email == settings.corpus_owner_email,
                )
            )
        )
        .scalars()
        .all()
    )
    assert {str(chunk_id) for chunk_id in owner_chunk_ids} == cited_ids
    # cited_passages are the exact DB rows, not model-invented text
    assert {str(r.id): r.content for r in rows} == {
        p.chunk_id: p.content for p in result.cited_passages
    }
    for citation in result.citations:
        passage = next(
            p for p in result.cited_passages if p.chunk_id == citation.chunk_id
        )
        assert " ".join(citation.quote.split()) in " ".join(passage.content.split())


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
