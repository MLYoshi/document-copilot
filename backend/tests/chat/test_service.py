from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.chat import service

pytestmark = pytest.mark.asyncio

CREATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


async def test_create_thread_returns_thread_with_id_and_timestamps(monkeypatch):
    user_id = uuid4()
    session = AsyncMock()
    created = {}

    async def fake_create(sess, user_id, title):
        created.update(user_id=user_id, title=title)
        return SimpleNamespace(
            id=uuid4(), user_id=user_id, title=title,
            created_at=CREATED_AT, updated_at=UPDATED_AT,
        )

    monkeypatch.setattr(service.chat_threads, "create", fake_create)

    thread = await service.create_thread(session, user_id=user_id, title=" demo ")

    assert created == {"user_id": user_id, "title": "demo"}
    assert isinstance(thread.id, UUID)
    assert thread.created_at == CREATED_AT
    assert thread.updated_at == UPDATED_AT


async def test_list_threads_returns_current_users_threads(monkeypatch):
    user_id = uuid4()
    session = AsyncMock()
    requested = {}

    async def fake_list_for_user(sess, user_id):
        requested["user_id"] = user_id
        return [
            SimpleNamespace(
                id=uuid4(), user_id=user_id, title=f"thread {n}",
                created_at=CREATED_AT, updated_at=UPDATED_AT,
            )
            for n in (1, 2)
        ]

    monkeypatch.setattr(service.chat_threads, "list_for_user", fake_list_for_user)

    threads = await service.list_threads(session, user_id=user_id)

    assert requested == {"user_id": user_id}
    assert [t.title for t in threads] == ["thread 1", "thread 2"]
    assert all(isinstance(t.id, UUID) for t in threads)


async def test_get_thread_returns_detail_for_owner(monkeypatch):
    user_id = uuid4()
    thread_id = uuid4()
    session = AsyncMock()
    requested = {}

    async def fake_get_for_user(sess, thread_id, user_id):
        requested.update(thread_id=thread_id, user_id=user_id)
        return SimpleNamespace(
            id=thread_id, user_id=user_id, title="my thread",
            created_at=CREATED_AT, updated_at=UPDATED_AT,
        )

    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    thread = await service.get_thread(session, thread_id=thread_id, user_id=user_id)

    assert requested == {"thread_id": thread_id, "user_id": user_id}
    assert thread.title == "my thread"
    assert thread.created_at == CREATED_AT


async def test_get_thread_returns_404_for_missing_or_foreign_thread(monkeypatch):
    session = AsyncMock()

    async def fake_get_for_user(sess, thread_id, user_id):
        return None

    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_thread(
            session, thread_id=uuid4(), user_id=uuid4()
        )
    assert exc_info.value.status_code == 404
