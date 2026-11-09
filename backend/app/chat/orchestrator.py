import os
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.agent import build_agent
from app.assistant.outputs import AnswerDraft
from app.core.config import settings
from app.core.embeddings import get_embedding
from app.retrieval.retriever import PgVectorRetriever


def _tracing_config(user_id: UUID, thread_id: UUID) -> dict:
    # search_filings is capped at 3 calls (~8 supersteps); 12 leaves margin
    config: dict = {"recursion_limit": 12}
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        from langfuse.langchain import CallbackHandler

        # Langfuse SDK reads credentials from env; bridge our .env settings.
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        config["callbacks"] = [CallbackHandler()]
        config["metadata"] = {
            "langfuse_session_id": str(thread_id),
            "langfuse_user_id": str(user_id),
        }
    return config


async def answer_question(
    session: AsyncSession,
    *,
    user_id: UUID,
    thread_id: UUID,
    question: str,
    agent=None,
) -> AnswerDraft:
    graph = (
        agent
        if agent is not None
        else build_agent(PgVectorRetriever(session, get_embedding))
    )
    result = await graph.ainvoke(
        {"messages": [("user", question)]},
        config=_tracing_config(user_id, thread_id),
    )
    return cast(AnswerDraft, result["structured_response"])
