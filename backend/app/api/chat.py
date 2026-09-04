from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.chat import service
from app.chat.schemas import (
    CreateThreadRequest,
    MessagePublic,
    SendMessageRequest,
    ThreadPublic,
)
from app.chat.streaming import build_answer_events
from app.database.session import get_session

router = APIRouter(prefix="/threads", tags=["chat"])


@router.post("", response_model=ThreadPublic, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: CreateThreadRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> ThreadPublic:
    return await service.create_thread(session, user_id=current_user.id, title=body.title)


@router.get("", response_model=list[ThreadPublic])
async def list_threads(
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> list[ThreadPublic]:
    return await service.list_threads(session, user_id=current_user.id)


@router.get("/{thread_id}", response_model=ThreadPublic)
async def get_thread(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> ThreadPublic:
    return await service.get_thread(session, thread_id=thread_id, user_id=current_user.id)


@router.post("/{thread_id}/messages/stream")
async def stream_message(
    thread_id: UUID,
    body: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> StreamingResponse:
    # 整轮编排与持久化在 handler 内完成，错误在响应头发送前以标准
    # HTTP 状态码返回；帧序列由 streaming.py 集中编码
    grounded = await service.answer_in_thread(
        session, user_id=current_user.id, thread_id=thread_id, question=body.question
    )
    return StreamingResponse(
        iter(build_answer_events(grounded)), media_type="text/event-stream"
    )


@router.get("/{thread_id}/messages", response_model=list[MessagePublic])
async def list_messages(
    thread_id: UUID,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
) -> list[MessagePublic]:
    return await service.list_messages(
        session, user_id=current_user.id, thread_id=thread_id
    )
