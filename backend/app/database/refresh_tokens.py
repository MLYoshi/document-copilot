import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import RefreshToken


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Create a new refresh token record and return the plaintext token."""
    token = secrets.token_hex(32)
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await session.commit()
    return token


async def rotate(session: AsyncSession, token: str) -> tuple[uuid.UUID, str] | None:
    """Atomically consume a refresh token and issue its replacement.

    The SELECT-and-DELETE collapse into a single ``DELETE ... RETURNING`` so a
    concurrent replay of the same token can never yield two valid sessions.
    Returns ``(user_id, new_token)``, or ``None`` when the token is unknown or
    expired.
    """
    new_token = secrets.token_hex(32)
    result = await session.execute(
        delete(RefreshToken)
        .where(RefreshToken.token_hash == _hash_token(token))
        .returning(RefreshToken.user_id, RefreshToken.expires_at)
    )
    row = result.first()
    if row is None or row.expires_at <= datetime.now(UTC):
        await session.rollback()
        return None
    session.add(
        RefreshToken(
            user_id=row.user_id,
            token_hash=_hash_token(new_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
    )
    await session.commit()
    return row.user_id, new_token


async def revoke_for_user(session: AsyncSession, token: str, user_id: uuid.UUID) -> bool:
    """Delete a refresh token if and only if it belongs to ``user_id``."""
    result = await session.execute(
        delete(RefreshToken).where(
            RefreshToken.token_hash == _hash_token(token),
            RefreshToken.user_id == user_id,
        )
    )
    await session.commit()
    return result.rowcount > 0
