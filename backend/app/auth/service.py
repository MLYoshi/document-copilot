"""Supabase Auth 注册、登录、刷新、登出与令牌校验。"""
from fastapi import HTTPException, status
from supabase_auth.errors import AuthApiError
from supabase_auth.types import Session, User

from app.auth.schemas import TokenPair, UserPublic
from app.auth.supabase import get_supabase_client


def _tokens(session: Session | None) -> TokenPair:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication failed")
    return TokenPair(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


async def register(email: str, password: str) -> UserPublic:
    try:
        response = await get_supabase_client().auth.sign_up(
            {"email": email, "password": password}
        )
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "registration failed") from exc
    if response.user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "registration failed")
    return UserPublic(id=response.user.id, email=response.user.email or email)


async def login(email: str, password: str) -> TokenPair:
    try:
        response = await get_supabase_client().auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except AuthApiError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid email or password"
        ) from exc
    return _tokens(response.session)


async def refresh(refresh_token: str) -> TokenPair:
    try:
        response = await get_supabase_client().auth.refresh_session(refresh_token)
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token") from exc
    return _tokens(response.session)


async def get_user(access_token: str) -> User:
    try:
        response = await get_supabase_client().auth.get_user(access_token)
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid access token") from exc
    if response is None or response.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid access token")
    return response.user


async def logout(access_token: str) -> None:
    try:
        await get_supabase_client().auth.admin.sign_out(access_token)
    except AuthApiError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "logout failed") from exc
