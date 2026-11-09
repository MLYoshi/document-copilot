import pytest
from sqlalchemy import desc, select, text

from app.chat.service import stream_answer_in_thread
from app.database import chat_threads
from app.database.models import ChatMessage, MessageRole
from app.database.session import get_session, session_factory

pytestmark = pytest.mark.integration


async def test_real_agent_persists_answer_and_closes_cleanly():

    async for session in get_session():
        result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
        user_id = result.scalar_one()
        thread = await chat_threads.create(session, user_id=user_id, title="repro")
        thread_id = thread.id

        events = await stream_answer_in_thread(
            session,
            user_id=user_id,
            thread_id=thread_id,
            question="What was Apple's total net sales in fiscal 2023?",
        )
        frames = [frame async for frame in events]
        assert any('"type": "text-delta"' in frame for frame in frames)
        assert not any('"type": "error"' in frame for frame in frames)


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
