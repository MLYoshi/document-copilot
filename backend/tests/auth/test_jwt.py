from uuid import uuid4

import pytest

from app.auth import jwt as auth_jwt


def test_create_and_decode_roundtrip():
    user_id = uuid4()
    token = auth_jwt.create_access_token(user_id)
    assert auth_jwt.decode_access_token(token) == user_id


def test_decode_rejects_garbage():
    with pytest.raises(auth_jwt.InvalidTokenError):
        auth_jwt.decode_access_token("not-a-jwt")


def test_decode_rejects_expired_token(monkeypatch):
    monkeypatch.setattr("app.config.settings.jwt_access_token_expire_minutes", -1)
    token = auth_jwt.create_access_token(uuid4())
    with pytest.raises(auth_jwt.InvalidTokenError):
        auth_jwt.decode_access_token(token)


def test_decode_rejects_wrong_signature(monkeypatch):
    token = auth_jwt.create_access_token(uuid4())
    monkeypatch.setattr("app.config.settings.jwt_secret_key", "other-secret")
    with pytest.raises(auth_jwt.InvalidTokenError):
        auth_jwt.decode_access_token(token)
