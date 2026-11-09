from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import orchestrator
from app.chat.schemas import MessagePublic, ThreadPublic
from app.chat.streaming import answer_event
from app.database import chat_messages, chat_threads
from app.database.session import session_factory

logger = structlog.get_logger()


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


async def stream_answer_in_thread(
    session: AsyncSession,
    *,
    user_id: UUID,
    thread_id: UUID,
    question: str,
) -> AsyncIterator[str]:
    await _require_thread(session, thread_id, user_id)
    await chat_messages.save_user_message(session, thread_id, question)

    async def events() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        draft = None
        try:
            async for item in orchestrator.stream_answer(
                user_id=user_id,
                thread_id=thread_id,
                question=question,
            ):
                if isinstance(item, str):
                    answer_parts.append(item)
                    yield answer_event({"type": "text-delta", "delta": item})
                else:
                    draft = item

            if draft is None:
                raise RuntimeError("The agent did not produce an answer")
            answer = "".join(answer_parts) or draft.answer
            if not answer_parts:
                yield answer_event({"type": "text-delta", "delta": answer})
            citations = [(UUID(c.passage_id), c.quote) for c in draft.citations]
            async with session_factory() as fresh_session:
                await chat_messages.save_assistant_turn(
                    fresh_session, thread_id, answer, citations
                )
            yield answer_event(
                {
                    "type": "citations",
                    "citations": [
                        {"passage_id": str(passage_id), "ordinal": ordinal, "quote": quote}
                        for ordinal, (passage_id, quote) in enumerate(citations)
                    ],
                }
            )
        except Exception as exc:
            logger.exception("answer_stream_failed", thread_id=str(thread_id), error=str(exc))
            yield answer_event({"type": "error", "message": str(exc)})
        yield answer_event({"type": "finish"})

    return events()


async def list_messages(
    session: AsyncSession, user_id: UUID, thread_id: UUID
) -> list[MessagePublic]:
    await _require_thread(session, thread_id, user_id)
    messages = await chat_messages.list_for_thread(
        session, thread_id=thread_id, user_id=user_id
    )
    return [MessagePublic.model_validate(m) for m in messages]
