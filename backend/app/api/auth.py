from fastapi import APIRouter, Depends, status

from app.auth import service
from app.auth.dependencies import get_current_user, oauth2_scheme
from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED
)
async def register(body: RegisterRequest) -> UserPublic:
    return await service.register(email=body.email, password=body.password)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest) -> TokenPair:
    return await service.login(email=body.email, password=body.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    return await service.refresh(refresh_token=body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    access_token: str = Depends(oauth2_scheme),
    current_user=Depends(get_current_user),
) -> None:
    await service.logout(access_token=access_token)


@router.get("/me", response_model=UserPublic)
async def me(current_user=Depends(get_current_user)) -> UserPublic:
    return UserPublic(id=current_user.id, email=current_user.email)
