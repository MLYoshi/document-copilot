from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import json

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.assistant.outputs import Citation, GroundedAnswer, SourcePassage
from app.auth.dependencies import get_current_user
from app.chat import service as chat_service
from app.database.session import get_session
from app.main import app

CREATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

CHUNK_ID = "11111111-1111-1111-1111-111111111111"

FAKE_ANSWER = GroundedAnswer(
    answer="Revenue grew 12% year over year.",
    citations=[Citation(chunk_id=CHUNK_ID, quote="Revenue grew 12%")],
    cited_passages=[
        SourcePassage(
            chunk_id=CHUNK_ID,
            document_id="22222222-2222-2222-2222-222222222222",
            chunk_index=3,
            content="Revenue grew 12% year over year, driven by ...",
            score=0.87,
            section_path="Item 7 > Results of Operations",
            title="Annual Report",
            ticker="ACME",
            form="10-K",
            filing_date="2026-02-20",
            source_url="https://example.com/acme-10k",
        )
    ],
    evidence_sufficient=True,
)


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


def _parse_sse_frames(text: str) -> list[dict]:
    frames = []
    for chunk in text.split("\n\n"):
        if not chunk:
            continue
        assert chunk.startswith("data: ")
        frames.append(json.loads(chunk.removeprefix("data: ")))
    return frames


def test_stream_message_requires_authentication(client):
    response = client.post(
        f"/threads/{uuid4()}/messages/stream", json={"question": "q"}
    )
    assert response.status_code == 401


def test_list_messages_requires_authentication(client):
    response = client.get(f"/threads/{uuid4()}/messages")
    assert response.status_code == 401


def test_stream_message_returns_sse_frame_sequence(
    client, authed_client, monkeypatch
):
    user, thread_id = authed_client, uuid4()

    async def fake_answer_in_thread(sess, **kwargs):
        assert kwargs["user_id"] == user.id
        assert kwargs["thread_id"] == thread_id
        assert kwargs["question"] == "How did revenue grow?"
        return FAKE_ANSWER

    monkeypatch.setattr(chat_service, "answer_in_thread", fake_answer_in_thread)

    response = client.post(
        f"/threads/{thread_id}/messages/stream",
        json={"question": "How did revenue grow?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    frames = _parse_sse_frames(response.text)
    assert [f["type"] for f in frames] == [
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "data-citations",
        "data-evidence",
        "finish",
    ]
    assert frames[2]["delta"] == FAKE_ANSWER.answer
    citations = frames[4]["data"]
    assert citations[0]["chunk_id"] == CHUNK_ID
    assert citations[0]["title"] == "Annual Report"
    assert citations[0]["section_path"] == "Item 7 > Results of Operations"
    assert frames[5]["data"] == {"evidence_sufficient": True}


def test_stream_message_rejects_empty_question(client, authed_client):
    response = client.post(
        f"/threads/{uuid4()}/messages/stream", json={"question": ""}
    )
    assert response.status_code == 422


def test_stream_message_returns_404_for_foreign_thread(
    client, authed_client, monkeypatch
):
    async def fake_answer_in_thread(sess, **kwargs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")

    monkeypatch.setattr(chat_service, "answer_in_thread", fake_answer_in_thread)

    response = client.post(
        f"/threads/{uuid4()}/messages/stream", json={"question": "q"}
    )

    assert response.status_code == 404


def test_stream_message_maps_grounding_failure_to_502(
    client, authed_client, monkeypatch
):
    async def fake_answer_in_thread(sess, **kwargs):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "证据不足或引用校验失败，已拒绝返回无据答案",
        )

    monkeypatch.setattr(chat_service, "answer_in_thread", fake_answer_in_thread)

    response = client.post(
        f"/threads/{uuid4()}/messages/stream", json={"question": "q"}
    )

    assert response.status_code == 502
    assert "证据不足" in response.json()["detail"]


def test_list_messages_returns_history_with_citations(
    client, authed_client, monkeypatch
):
    user, thread_id = authed_client, uuid4()

    def make_message(role, content, citations=()):
        return SimpleNamespace(
            id=uuid4(),
            thread_id=thread_id,
            role=role,
            content=content,
            created_at=CREATED_AT,
            citations=[
                SimpleNamespace(chunk_id=UUID(chunk_id), ordinal=i, quote=quote)
                for i, (chunk_id, quote) in enumerate(citations)
            ],
        )

    async def fake_get_for_user(sess, thread_id, user_id):
        assert user_id == user.id
        return SimpleNamespace(id=thread_id)

    async def fake_list_for_thread(sess, thread_id, user_id):
        return [
            make_message("user", "How did revenue grow?"),
            make_message(
                "assistant",
                "Revenue grew 12% year over year.",
                citations=[(CHUNK_ID, "Revenue grew 12%")],
            ),
        ]

    monkeypatch.setattr(chat_service.chat_threads, "get_for_user", fake_get_for_user)
    monkeypatch.setattr(
        chat_service.chat_messages, "list_for_thread", fake_list_for_thread
    )

    response = client.get(f"/threads/{thread_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["citations"] == []
    assert body[1]["citations"] == [
        {"chunk_id": CHUNK_ID, "ordinal": 0, "quote": "Revenue grew 12%"}
    ]


def test_list_messages_returns_404_for_foreign_thread(
    client, authed_client, monkeypatch
):
    async def fake_get_for_user(sess, thread_id, user_id):
        return None

    monkeypatch.setattr(chat_service.chat_threads, "get_for_user", fake_get_for_user)

    response = client.get(f"/threads/{uuid4()}/messages")

    assert response.status_code == 404
