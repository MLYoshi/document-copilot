from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.chat import service as chat_service
from app.database.session import get_session
from app.main import app

CREATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def authed_client(monkeypatch):
    user = SimpleNamespace(id=uuid4(), email="analyst@example.com")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    yield user
    app.dependency_overrides.clear()


def test_create_thread_requires_authentication(client):
    response = client.post("/threads", json={"title": "demo"})
    assert response.status_code == 401


def test_list_threads_requires_authentication(client):
    response = client.get("/threads")
    assert response.status_code == 401


def test_get_thread_requires_authentication(client):
    response = client.get(f"/threads/{uuid4()}")
    assert response.status_code == 401


def test_create_thread_returns_201_with_thread_body(client, authed_client, monkeypatch):
    async def fake_create(sess, user_id, title):
        return SimpleNamespace(
            id=uuid4(), user_id=user_id, title=title,
            created_at=CREATED_AT, updated_at=CREATED_AT,
        )

    monkeypatch.setattr(chat_service.chat_threads, "create", fake_create)

    response = client.post("/threads", json={"title": "  demo  "})

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["title"] == "demo"
    assert body["created_at"] == "2026-08-30T12:00:00Z"


def test_list_threads_returns_current_users_threads(client, authed_client, monkeypatch):
    user = authed_client

    async def fake_list_for_user(sess, user_id):
        assert user_id == user.id
        return [
            SimpleNamespace(
                id=uuid4(), user_id=user_id, title=f"thread {n}",
                created_at=CREATED_AT, updated_at=CREATED_AT,
            )
            for n in (1, 2)
        ]

    monkeypatch.setattr(chat_service.chat_threads, "list_for_user", fake_list_for_user)

    response = client.get("/threads")

    assert response.status_code == 200
    body = response.json()
    assert [t["title"] for t in body] == ["thread 1", "thread 2"]


def test_get_thread_returns_detail_for_owner(client, authed_client, monkeypatch):
    user = authed_client
    thread_id = uuid4()

    async def fake_get_for_user(sess, thread_id, user_id):
        assert user_id == user.id
        return SimpleNamespace(
            id=thread_id, user_id=user_id, title="my thread",
            created_at=CREATED_AT, updated_at=CREATED_AT,
        )

    monkeypatch.setattr(chat_service.chat_threads, "get_for_user", fake_get_for_user)

    response = client.get(f"/threads/{thread_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "my thread"


def test_get_thread_returns_404_for_foreign_thread(client, authed_client, monkeypatch):
    async def fake_get_for_user(sess, thread_id, user_id):
        return None

    monkeypatch.setattr(chat_service.chat_threads, "get_for_user", fake_get_for_user)

    response = client.get(f"/threads/{uuid4()}")

    assert response.status_code == 404
