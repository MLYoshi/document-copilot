"""聊天线程业务逻辑。

函数直接操作 AsyncSession 与 database/ 仓储函数，不建类。
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.outputs import GroundedAnswer
from app.chat import orchestrator
from app.chat.schemas import MessagePublic, ThreadPublic
from app.database import chat_messages, chat_threads
from app.grounding.validator import GroundingError


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
    # 404 而非 403：非属主与不存在不可区分，避免泄露资源存在性
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return ThreadPublic.model_validate(thread)


async def _require_thread(
    session: AsyncSession, thread_id: UUID, user_id: UUID
) -> None:
    # 404 而非 403：非属主与不存在不可区分，避免泄露资源存在性
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
) -> GroundedAnswer:
    """Run one grounded RAG turn and persist both sides of the conversation.

    Ownership is checked first (404 on miss). The user message commits before
    the orchestrator runs, so a failed answer still leaves the question on
    record. GroundingError maps to a controlled 502 — an unfounded answer is
    never returned — and no assistant message is written in that case.
    """
    await _require_thread(session, thread_id, user_id)

    await chat_messages.save_user_message(session, thread_id, question)

    try:
        grounded = await orchestrator.answer_question(
            session,
            user_id=user_id,
            thread_id=thread_id,
            question=question,
            agent=agent,
        )
    except GroundingError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "证据不足或引用校验失败，已拒绝返回无据答案",
        ) from exc

    await chat_messages.save_assistant_turn(
        session,
        thread_id,
        grounded.answer,
        [(UUID(c.chunk_id), c.quote) for c in grounded.citations],
    )
    return grounded


async def list_messages(
    session: AsyncSession, user_id: UUID, thread_id: UUID
) -> list[MessagePublic]:
    await _require_thread(session, thread_id, user_id)
    messages = await chat_messages.list_for_thread(
        session, thread_id=thread_id, user_id=user_id
    )
    return [MessagePublic.model_validate(m) for m in messages]
