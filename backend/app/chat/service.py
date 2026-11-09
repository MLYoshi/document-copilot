from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import AnswerDraft
from app.chat import orchestrator
from app.chat.schemas import MessagePublic, ThreadPublic
from app.database import chat_messages, chat_threads
from app.database.session import session_factory


async def create_thread(
    session: AsyncSession, user_id: UUID, title: str
) -> ThreadPublic:
    thread = await chat_threads.create(
        session, user_id=user_id, title=title.strip()
    )
    return ThreadPublic.model_validate(thread)


async def list_threads(session: AsyncSession, user_id: UUID) -> list[ThreadPublic]:
    threads = await chat_threads.list_for_user(session, user_id=user_id)
    return [ThreadPublic.model_validate(t) for t in threads]


async def get_thread(session: AsyncSession, thread_id: UUID, user_id: UUID) -> ThreadPublic:
    thread = await chat_threads.get_for_user(session, thread_id=thread_id, user_id=user_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return ThreadPublic.model_validate(thread)


async def _require_thread(
    session: AsyncSession, thread_id: UUID, user_id: UUID
) -> None:
    thread = await chat_threads.get_for_user(
        session, thread_id=thread_id, user_id=user_id
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")


async def answer_in_thread(
    session: AsyncSession,
    *,
    user_id: UUID,
    thread_id: UUID,
    question: str,
    agent=None,
) -> AnswerDraft:
    await _require_thread(session, thread_id, user_id)

    await chat_messages.save_user_message(session, thread_id, question)

    draft = await orchestrator.answer_question(
        session,
        user_id=user_id,
        thread_id=thread_id,
        question=question,
        agent=agent,
    )

    # The LLM call above can take tens of seconds; the original session's
    # connection may be closed by the pooler while idle. Persist the answer
    # with a fresh session/connection instead of the stale one.
    async with session_factory() as fresh_session:
        await chat_messages.save_assistant_turn(
            fresh_session,
            thread_id,
            draft.answer,
            [(UUID(c.passage_id), c.quote) for c in draft.citations],
        )
    return draft


async def list_messages(
    session: AsyncSession, user_id: UUID, thread_id: UUID
) -> list[MessagePublic]:
    await _require_thread(session, thread_id, user_id)
    messages = await chat_messages.list_for_thread(
        session, thread_id=thread_id, user_id=user_id
    )
    return [MessagePublic.model_validate(m) for m in messages]
