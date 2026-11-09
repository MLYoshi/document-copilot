"""End-to-end regression: the real (non-mocked) agent path must persist the answer
and the request-scoped session must close cleanly even after a long LLM call.

Run with: uv run pytest tests/test_real_agent_repro.py -m integration -s
Requires DATABASE_URL and OPENROUTER_API_KEY in .env.
"""
import pytest
from sqlalchemy import desc, select, text

from app.chat.service import answer_in_thread
from app.database import chat_threads
from app.database.models import ChatMessage, MessageRole
from app.database.session import get_session, session_factory

pytestmark = pytest.mark.integration


async def test_real_agent_persists_answer_and_closes_cleanly():
    # get_session() mirrors the FastAPI dependency used by the stream route.
    async for session in get_session():
        result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
        user_id = result.scalar_one()
        thread = await chat_threads.create(session, user_id=user_id, title="repro")
        thread_id = thread.id

        draft = await answer_in_thread(
            session,
            user_id=user_id,
            thread_id=thread_id,
            question="What was Apple's total net sales in fiscal 2023?",
            # agent NOT mocked -> real LLM + embedding + retrieval path
        )
        assert draft.answer
    # Exiting get_session must not raise even though the LLM call idled the conn.

    async with session_factory() as check:
        result = await check.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(desc(ChatMessage.created_at))
        )
        messages = list(result.scalars().all())

    roles = {m.role for m in messages}
    assert MessageRole.user in roles
    assert MessageRole.assistant in roles, "assistant answer was not persisted"
    print(f"\nPersisted {len(messages)} messages for thread_id={thread_id}")
