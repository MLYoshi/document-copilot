import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChatThread


async def create(session: AsyncSession, user_id: uuid.UUID, title: str) -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title)
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[ChatThread]:
    result = await session.execute(
        select(ChatThread)
        .where(ChatThread.user_id == user_id)
        .order_by(ChatThread.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_for_user(
    session: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> ChatThread | None:
    result = await session.execute(
        select(ChatThread).where(
            ChatThread.id == thread_id, ChatThread.user_id == user_id
        )
    )
    return result.scalar_one_or_none()
