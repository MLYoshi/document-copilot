"""Verify that asking one question really persists both messages to the database.

Run with: uv run pytest tests/test_message_persistence.py -m integration -s
Requires DATABASE_URL in .env. The agent is mocked, so no LLM credentials needed.
"""
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.assistant.outputs import AnswerDraft, Citation
from app.chat.service import answer_in_thread
from app.database import chat_threads
from app.database.models import ChatMessage, MessageRole
from app.database.session import session_factory

pytestmark = pytest.mark.integration


async def _pick_existing_user_id(session):
    # chat_threads.user_id -> auth.users.id (Supabase), so reuse a real user.
    result = await session.execute(text("SELECT id FROM auth.users LIMIT 1"))
    user_id = result.scalar_one_or_none()
    assert user_id is not None, "No row in auth.users; sign up a user first."
    return user_id


class FakeAgent:
    """Minimal stand-in for the LangGraph agent; returns a fixed AnswerDraft."""

    def __init__(self, draft: AnswerDraft):
        self._draft = draft

    async def ainvoke(self, input, config=None):
        return {"structured_response": self._draft}


async def test_question_and_answer_persist_to_database():
    question = "What was Apple's total net sales in fiscal 2023?"
    answer_text = "Apple's total net sales in fiscal 2023 were $383.3 billion."
    passage_id = uuid4()

    draft = AnswerDraft(
        answer=answer_text,
        citations=[Citation(passage_id=str(passage_id), quote="383,285 million")],
    )
    agent = FakeAgent(draft)

    async with session_factory() as session:
        user_id = await _pick_existing_user_id(session)
        thread = await chat_threads.create(session, user_id=user_id, title="Test thread")

        returned = await answer_in_thread(
            session,
            user_id=user_id,
            thread_id=thread.id,
            question=question,
            agent=agent,
        )
        assert returned.answer == answer_text

        # Read back straight from the database in a fresh query.
        result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.created_at)
        )
        messages = list(result.scalars().all())

    assert len(messages) == 2

    user_msg = messages[0]
    assert user_msg.role == MessageRole.user
    assert user_msg.content == question
    assert user_msg.thread_id == thread.id

    assistant_msg = messages[1]
    assert assistant_msg.role == MessageRole.assistant
    assert assistant_msg.content == answer_text
    assert assistant_msg.thread_id == thread.id
    assert assistant_msg.citations[0]["passage_id"] == str(passage_id)
    assert assistant_msg.citations[0]["quote"] == "383,285 million"

    print(f"\nPersisted thread_id={thread.id}")
    print(f"  user:      {user_msg.content}")
    print(f"  assistant: {assistant_msg.content}")
