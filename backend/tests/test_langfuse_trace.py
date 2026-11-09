"""Minimal end-to-end check: ask one real question so a trace shows up in Langfuse.

Run with: uv run pytest tests/test_langfuse_trace.py -m integration -s
Requires OPENROUTER_API_KEY, DATABASE_URL and LANGFUSE_* in .env.
"""
from uuid import uuid4

import pytest

from app.chat.orchestrator import answer_question
from app.database.session import session_factory

pytestmark = pytest.mark.integration


async def test_question_produces_langfuse_trace():
    user_id = uuid4()
    thread_id = uuid4()

    async with session_factory() as session:
        draft = await answer_question(
            session,
            user_id=user_id,
            thread_id=thread_id,
            question="What was Apple's total net sales in fiscal 2023?",
        )

    assert draft.answer

    # Langfuse batches in the background; flush so the trace is sent now.
    from langfuse import get_client

    get_client().flush()

    print(f"\nCheck Langfuse for session_id={thread_id} user_id={user_id}")
