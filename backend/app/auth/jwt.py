from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.config import settings


class InvalidTokenError(Exception):
    """Raised when a JWT is malformed, expired, or not an access token."""


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            # Missing claims in an otherwise validly-signed token → 401, not 500.
            require=["exp", "sub"],
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    if payload.get("type") != "access":
        raise InvalidTokenError
    return UUID(payload["sub"])
