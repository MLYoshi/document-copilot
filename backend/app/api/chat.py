from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.chat import service
from app.chat.schemas import CreateThreadRequest, ThreadPublic
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
