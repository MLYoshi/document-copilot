"""聊天线程业务逻辑。

函数直接操作 AsyncSession 与 database/ 仓储函数，不建类。
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.schemas import ThreadPublic
from app.database import chat_threads


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
