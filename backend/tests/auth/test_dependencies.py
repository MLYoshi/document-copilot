from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import dependencies
from app.auth import jwt as auth_jwt
from app.auth.dependencies import get_current_user

pytestmark = pytest.mark.asyncio


async def test_valid_token_resolves_user(monkeypatch):
    user_id = uuid4()
    token = auth_jwt.create_access_token(user_id)
    user = SimpleNamespace(id=user_id, email="analyst@example.com")

    async def fake_get_by_id(sess, uid):
        assert uid == user_id
        return user

    monkeypatch.setattr(dependencies.users, "get_by_id", fake_get_by_id)
    result = await get_current_user(token=token, session=AsyncMock())
    assert result is user


async def test_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="garbage", session=AsyncMock())
    assert exc_info.value.status_code == 401


async def test_unknown_user_raises_401(monkeypatch):
    token = auth_jwt.create_access_token(uuid4())

    async def fake_get_by_id(sess, uid):
        return None

    monkeypatch.setattr(dependencies.users, "get_by_id", fake_get_by_id)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=token, session=AsyncMock())
    assert exc_info.value.status_code == 401


async def test_refresh_token_is_not_accepted_as_access_token():
    """A refresh token plaintext must not authenticate as a JWT."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="opaque-refresh-token", session=AsyncMock())
    assert exc_info.value.status_code == 401
