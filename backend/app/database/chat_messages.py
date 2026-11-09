import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChatMessage, ChatThread, MessageRole


async def list_for_thread(
    session: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .where(ChatMessage.thread_id == thread_id, ChatThread.user_id == user_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def save_user_message(
    session: AsyncSession, thread_id: uuid.UUID, content: str
) -> ChatMessage:
    message = ChatMessage(thread_id=thread_id, role=MessageRole.user, content=content)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def save_assistant_turn(
    session: AsyncSession,
    thread_id: uuid.UUID,
    content: str,
    citations: Sequence[tuple[uuid.UUID, str | None]],
) -> ChatMessage:
    message = ChatMessage(
        thread_id=thread_id,
        role=MessageRole.assistant,
        content=content,
        citations=[
            {"passage_id": str(passage_id), "ordinal": ordinal, "quote": quote}
            for ordinal, (passage_id, quote) in enumerate(citations)
        ],
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message
