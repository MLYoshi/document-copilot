"""注册/登录/刷新/登出业务逻辑。

函数直接操作 AsyncSession 与 database/ 仓储函数，不建类。
"""
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import jwt as auth_jwt
from app.auth import password
from app.auth.schemas import TokenPair, UserPublic
from app.database import refresh_tokens, users
from app.database.models import User

log = structlog.get_logger()

# Precomputed bcrypt hash used to equalize timing when the user does not exist,
# so login latency no longer leaks whether an email is registered.
_DUMMY_PASSWORD_HASH = (
    "$2b$12$C6UzMDM.H6dfI/f/IKcEe.WT8FiFbBoZg0d/8FjVvcnXaIzZGpO8C"
)


def _to_public(user: User) -> UserPublic:
    return UserPublic(id=user.id, email=user.email)


async def register(session: AsyncSession, email: str, password_plaintext: str) -> UserPublic:
    password_hash = await password.hash_password(password_plaintext)
    try:
        user = await users.create(session, email=email, password_hash=password_hash)
    except users.UserEmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    log.info("auth.register", user_id=str(user.id))
    return _to_public(user)


async def login(session: AsyncSession, email: str, password_plaintext: str) -> TokenPair:
    user = await users.get_by_email(session, email)
    stored_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    if not await password.verify_password(password_plaintext, stored_hash) or user is None:
        log.info("auth.login_failed", email_domain=email.rpartition("@")[2])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    refresh = await refresh_tokens.issue(session, user.id)
    log.info("auth.login", user_id=str(user.id))
    return TokenPair(access_token=auth_jwt.create_access_token(user.id), refresh_token=refresh)


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPair:
    rotated = await refresh_tokens.rotate(session, refresh_token)
    if rotated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    user_id, new_refresh = rotated
    return TokenPair(access_token=auth_jwt.create_access_token(user_id), refresh_token=new_refresh)


async def logout(session: AsyncSession, refresh_token: str, user_id: uuid.UUID) -> None:
    if await refresh_tokens.revoke_for_user(session, refresh_token, user_id):
        log.info("auth.logout", user_id=str(user_id))
