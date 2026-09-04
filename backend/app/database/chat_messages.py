import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import ChatMessage, ChatThread, MessageCitation, MessageRole


async def list_for_thread(
    session: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> list[ChatMessage]:
    # Joining on chat_threads keeps the row-level isolation contract: querying
    # another user's thread_id yields an empty list, never its messages.
    result = await session.execute(
        select(ChatMessage)
        .join(ChatThread, ChatMessage.thread_id == ChatThread.id)
        .where(ChatMessage.thread_id == thread_id, ChatThread.user_id == user_id)
        .options(selectinload(ChatMessage.citations))
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def save_user_message(
    session: AsyncSession, thread_id: uuid.UUID, content: str
) -> ChatMessage:
    # Committed separately from the assistant turn so the question survives
    # even when answer generation fails afterwards.
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
    """Persist the assistant message and its ``(chunk_id, quote)`` citations
    in a single transaction, ordinals assigned in the given order."""
    message = ChatMessage(
        thread_id=thread_id, role=MessageRole.assistant, content=content
    )
    message.citations = [
        MessageCitation(chunk_id=chunk_id, ordinal=ordinal, quote=quote)
        for ordinal, (chunk_id, quote) in enumerate(citations)
    ]
    session.add(message)
    await session.commit()
    await session.refresh(message, ["citations"])
    return message
