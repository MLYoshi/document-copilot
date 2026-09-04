"""Orchestrator for the agent-loop grounded answer pipeline.

This is the public entry point wired behind HTTP. It assembles the
per-question dependencies and hands control to the agent, which retrieves
passages itself through its ``search_filings`` / ``read_chunks`` tools and
returns the validated :class:`GroundedAnswer`. Persistence (threads,
messages) is intentionally out of scope here.
"""

from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agent import get_agent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.core.embeddings import get_embedding
from app.grounding.validator import GroundingValidator
from app.retrieval.retriever import PgVectorRetriever


async def answer_question(
    session: AsyncSession,
    *,
    user_id: UUID,
    thread_id: UUID,
    question: str,
    agent=None,  # Agent[DocumentAgentDeps, ...]; injectable for mock-LLM tests
) -> GroundedAnswer:
    """Answer ``question`` from passages the agent retrieves via its tools.

    Retrieval timing is the agent's decision, not the orchestrator's: the
    tool loop may search, reformulate, and read adjacent chunks for as long
    as it needs. The agent's ``output_validator`` already ran grounding
    validation against every passage accumulated during the run and resolved
    citations into ``cited_passages``, so its output is a
    :class:`GroundedAnswer` despite the declared ``AnswerDraft`` output type.
    Raises :class:`~app.grounding.validator.GroundingError` on any grounding
    violation — the caller maps it to a controlled error response.
    """
    deps = DocumentAgentDeps(
        user_id=user_id,
        thread_id=thread_id,
        retriever=PgVectorRetriever(session, get_embedding),
        grounding_validator=GroundingValidator(),
    )

    result = await (agent if agent is not None else get_agent()).run(
        question, deps=deps
    )
    return cast(GroundedAnswer, result.output)
