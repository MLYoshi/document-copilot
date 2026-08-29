from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import jwt as auth_jwt
from app.auth import service
from app.auth.password import hash_password
from app.database.users import UserEmailTakenError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    return AsyncMock()


@pytest.fixture
def fake_user():
    return SimpleNamespace(id=uuid4(), email="analyst@example.com", password_hash="")


async def test_register_creates_user(session, fake_user, monkeypatch):
    calls = {}

    async def fake_create(sess, email, password_hash):
        calls["email"] = email
        assert password_hash.startswith("$2")
        return fake_user

    monkeypatch.setattr(service.users, "create", fake_create)
    result = await service.register(session, "analyst@example.com", "password123")
    assert result.email == "analyst@example.com"
    assert calls["email"] == "analyst@example.com"


async def test_register_duplicate_email_raises_409(session, monkeypatch):
    async def fake_create(sess, email, password_hash):
        raise UserEmailTakenError(email)

    monkeypatch.setattr(service.users, "create", fake_create)
    with pytest.raises(HTTPException) as exc_info:
        await service.register(session, "taken@example.com", "password123")
    assert exc_info.value.status_code == 409


async def test_login_success_issues_token_pair(session, fake_user, monkeypatch):
    fake_user.password_hash = await hash_password("password123")

    async def fake_get_by_email(sess, email):
        return fake_user

    issued = []

    async def fake_issue(sess, user_id):
        issued.append(user_id)
        return "refresh-token-value"

    monkeypatch.setattr(service.users, "get_by_email", fake_get_by_email)
    monkeypatch.setattr(service.refresh_tokens, "issue", fake_issue)

    pair = await service.login(session, "analyst@example.com", "password123")
    assert pair.refresh_token == "refresh-token-value"
    assert issued == [fake_user.id]
    assert auth_jwt.decode_access_token(pair.access_token) == fake_user.id


async def test_login_unknown_email_raises_401(session, monkeypatch):
    async def fake_get_by_email(sess, email):
        return None

    monkeypatch.setattr(service.users, "get_by_email", fake_get_by_email)
    with pytest.raises(HTTPException) as exc_info:
        await service.login(session, "nobody@example.com", "password123")
    assert exc_info.value.status_code == 401


async def test_login_wrong_password_raises_401(session, fake_user, monkeypatch):
    fake_user.password_hash = await hash_password("correct-password")

    async def fake_get_by_email(sess, email):
        return fake_user

    monkeypatch.setattr(service.users, "get_by_email", fake_get_by_email)
    with pytest.raises(HTTPException) as exc_info:
        await service.login(session, "analyst@example.com", "wrong-password")
    assert exc_info.value.status_code == 401


async def test_refresh_rotates_token(session, monkeypatch):
    user_id = uuid4()
    rotated = []

    async def fake_rotate(sess, token):
        rotated.append(token)
        return user_id, "new-token"

    monkeypatch.setattr(service.refresh_tokens, "rotate", fake_rotate)

    pair = await service.refresh(session, "old-token")
    assert rotated == ["old-token"]
    assert pair.refresh_token == "new-token"
    assert auth_jwt.decode_access_token(pair.access_token) == user_id


async def test_refresh_unknown_or_expired_token_raises_401(session, monkeypatch):
    async def fake_rotate(sess, token):
        return None

    monkeypatch.setattr(service.refresh_tokens, "rotate", fake_rotate)
    with pytest.raises(HTTPException) as exc_info:
        await service.refresh(session, "bogus")
    assert exc_info.value.status_code == 401


async def test_logout_revokes_own_token(session, monkeypatch):
    user_id = uuid4()
    calls = []

    async def fake_revoke_for_user(sess, token, uid):
        calls.append((token, uid))
        return True

    monkeypatch.setattr(service.refresh_tokens, "revoke_for_user", fake_revoke_for_user)

    await service.logout(session, "my-token", user_id=user_id)
    assert calls == [("my-token", user_id)]


async def test_logout_ignores_other_users_token(session, monkeypatch):
    async def fake_revoke_for_user(sess, token, uid):
        return False

    monkeypatch.setattr(service.refresh_tokens, "revoke_for_user", fake_revoke_for_user)

    # foreign token: no error, just a no-op — the caller's tokens stay untouched
    await service.logout(session, "foreign-token", user_id=uuid4())
