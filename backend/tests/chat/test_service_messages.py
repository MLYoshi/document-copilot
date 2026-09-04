from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.assistant.outputs import Citation, GroundedAnswer
from app.chat import service
from app.database.models import MessageRole
from app.grounding.validator import GroundingError

pytestmark = pytest.mark.asyncio

CREATED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

CHUNK_A = uuid4()
CHUNK_B = uuid4()

FAKE_ANSWER = GroundedAnswer(
    answer="Revenue grew 12% year over year.",
    citations=[
        Citation(chunk_id=str(CHUNK_A), quote="Revenue grew 12%"),
        Citation(chunk_id=str(CHUNK_B), quote="12% year over year"),
    ],
    cited_passages=[],
    evidence_sufficient=True,
)


def make_message(role, content, citations=()):
    return SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        role=role,
        content=content,
        created_at=CREATED_AT,
        citations=[
            SimpleNamespace(
                chunk_id=chunk_id, ordinal=ordinal, quote=quote
            )
            for ordinal, (chunk_id, quote) in enumerate(citations)
        ],
    )


async def test_answer_in_thread_persists_user_then_assistant_turn(monkeypatch):
    user_id, thread_id = uuid4(), uuid4()
    session = AsyncMock()
    calls = []

    async def fake_save_user(sess, tid, content):
        calls.append(("save_user_message", tid, content))
        return SimpleNamespace(id=uuid4())

    async def fake_answer_question(sess, **kwargs):
        calls.append(("answer_question",))
        return FAKE_ANSWER

    async def fake_save_assistant(sess, tid, content, citations):
        calls.append(("save_assistant_turn", tid, content, citations))
        return SimpleNamespace(id=uuid4())

    async def fake_get_for_user(sess, thread_id, user_id):
        return SimpleNamespace(id=thread_id)

    monkeypatch.setattr(service.chat_messages, "save_user_message", fake_save_user)
    monkeypatch.setattr(
        service.orchestrator, "answer_question", fake_answer_question
    )
    monkeypatch.setattr(
        service.chat_messages, "save_assistant_turn", fake_save_assistant
    )
    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    grounded = await service.answer_in_thread(
        session, user_id=user_id, thread_id=thread_id, question="How did revenue grow?"
    )

    assert grounded is FAKE_ANSWER
    assert [c[0] for c in calls] == [
        "save_user_message",
        "answer_question",
        "save_assistant_turn",
    ]
    assert calls[0][1:] == (thread_id, "How did revenue grow?")
    # Citation chunk_ids must arrive as real UUIDs for the UUID column
    assert calls[2][3] == [
        (CHUNK_A, "Revenue grew 12%"),
        (CHUNK_B, "12% year over year"),
    ]


async def test_answer_in_thread_passes_agent_through(monkeypatch):
    session = AsyncMock()
    seen = {}

    async def fake_answer_question(sess, **kwargs):
        seen["agent"] = kwargs.get("agent")
        return FAKE_ANSWER

    async def fake_get_for_user(sess, thread_id, user_id):
        return SimpleNamespace(id=thread_id)

    monkeypatch.setattr(service.chat_messages, "save_user_message", AsyncMock())
    monkeypatch.setattr(service.chat_messages, "save_assistant_turn", AsyncMock())
    monkeypatch.setattr(
        service.orchestrator, "answer_question", fake_answer_question
    )
    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    sentinel = object()
    await service.answer_in_thread(
        session, user_id=uuid4(), thread_id=uuid4(), question="q", agent=sentinel
    )
    assert seen["agent"] is sentinel


async def test_answer_in_thread_returns_404_for_missing_or_foreign_thread(monkeypatch):
    session = AsyncMock()

    async def fake_get_for_user(sess, thread_id, user_id):
        return None

    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)
    orchestrator_stub = AsyncMock()
    monkeypatch.setattr(service.orchestrator, "answer_question", orchestrator_stub)
    monkeypatch.setattr(
        service.chat_messages, "save_user_message", AsyncMock()
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.answer_in_thread(
            session, user_id=uuid4(), thread_id=uuid4(), question="q"
        )
    assert exc_info.value.status_code == 404
    # Nothing ran: no retrieval, no persistence
    orchestrator_stub.assert_not_called()


async def test_answer_in_thread_maps_grounding_error_to_502(monkeypatch):
    session = AsyncMock()
    saved_assistant = AsyncMock()

    async def fake_answer_question(sess, **kwargs):
        raise GroundingError("cited chunk_id 'x' is not part of this round's retrieval set")

    async def fake_get_for_user(sess, thread_id, user_id):
        return SimpleNamespace(id=thread_id)

    monkeypatch.setattr(service.chat_messages, "save_user_message", AsyncMock())
    monkeypatch.setattr(
        service.orchestrator, "answer_question", fake_answer_question
    )
    monkeypatch.setattr(
        service.chat_messages, "save_assistant_turn", saved_assistant
    )
    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    with pytest.raises(HTTPException) as exc_info:
        await service.answer_in_thread(
            session, user_id=uuid4(), thread_id=uuid4(), question="q"
        )
    assert exc_info.value.status_code == 502
    # Controlled failure: the question is saved, but no half answer is persisted
    saved_assistant.assert_not_called()


async def test_list_messages_returns_messages_for_owner(monkeypatch):
    user_id, thread_id = uuid4(), uuid4()
    session = AsyncMock()
    requested = {}

    async def fake_get_for_user(sess, thread_id, user_id):
        return SimpleNamespace(id=thread_id)

    async def fake_list_for_thread(sess, thread_id, user_id):
        requested.update(thread_id=thread_id, user_id=user_id)
        return [
            make_message(MessageRole.user, "What was revenue growth?"),
            make_message(
                MessageRole.assistant,
                "Revenue grew 12% year over year.",
                citations=[(CHUNK_A, "Revenue grew 12%")],
            ),
        ]

    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)
    monkeypatch.setattr(
        service.chat_messages, "list_for_thread", fake_list_for_thread
    )

    messages = await service.list_messages(
        session, user_id=user_id, thread_id=thread_id
    )

    assert requested == {"thread_id": thread_id, "user_id": user_id}
    assert [m.role for m in messages] == [MessageRole.user, MessageRole.assistant]
    assert messages[0].citations == []
    assert messages[1].citations[0].chunk_id == CHUNK_A
    assert messages[1].citations[0].ordinal == 0
    assert all(isinstance(m.id, UUID) for m in messages)


async def test_list_messages_returns_404_for_missing_or_foreign_thread(monkeypatch):
    session = AsyncMock()

    async def fake_get_for_user(sess, thread_id, user_id):
        return None

    monkeypatch.setattr(service.chat_threads, "get_for_user", fake_get_for_user)

    with pytest.raises(HTTPException) as exc_info:
        await service.list_messages(session, user_id=uuid4(), thread_id=uuid4())
    assert exc_info.value.status_code == 404
