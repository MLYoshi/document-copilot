import os
from collections.abc import AsyncIterator
from typing import cast
from uuid import UUID

from app.assistant.agent import build_agent
from app.assistant.outputs import AnswerDraft
from app.core.config import settings
from app.core.embeddings import get_embedding
from app.retrieval.retriever import PgVectorRetriever


def _tracing_config(user_id: UUID, thread_id: UUID) -> dict:

    config: dict = {"recursion_limit": 12}
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        from langfuse.langchain import CallbackHandler


        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        config["callbacks"] = [CallbackHandler()]
        config["metadata"] = {
            "langfuse_session_id": str(thread_id),
            "langfuse_user_id": str(user_id),
        }
    return config


async def stream_answer(
    *,
    user_id: UUID,
    thread_id: UUID,
    question: str,
) -> AsyncIterator[str | AnswerDraft]:
    graph = build_agent(PgVectorRetriever(get_embedding))
    structured_response: AnswerDraft | None = None
    async for event in graph.astream_events(
        {"messages": [("user", question)]},
        config=_tracing_config(user_id, thread_id),
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            if event.get("metadata", {}).get("langgraph_node") != "model":
                continue
            content = event["data"]["chunk"].content
            if isinstance(content, str) and content:
                yield content
        elif event["event"] == "on_chain_end":
            output = event["data"].get("output")
            if isinstance(output, dict) and "structured_response" in output:
                structured_response = cast(AnswerDraft, output["structured_response"])
    if structured_response is None:
        raise RuntimeError("The agent did not produce a structured answer")
    yield structured_response
