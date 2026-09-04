"""Repository tests for app.database.chat_messages.

Touch a real PostgreSQL, hence the integration marker: repository behavior
(listing isolation, cascading citations, transaction boundaries) is exactly
what a mocked session would fake.
"""

import uuid

import pytest

from app.database import chat_messages
from app.database.models import (
    ChatThread,
    DocumentChunk,
    MessageRole,
    SourceDocument,
    User,
)

pytestmark = pytest.mark.integration


async def _make_user_thread(session, email: str) -> tuple[User, ChatThread]:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.flush()
    thread = ChatThread(user_id=user.id, title="t")
    session.add(thread)
    await session.commit()
    return user, thread


async def _make_chunk(session, user_id: uuid.UUID) -> DocumentChunk:
    document = SourceDocument(user_id=user_id, title="doc", content="markdown body")
    session.add(document)
    await session.flush()
    chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="passage")
    session.add(chunk)
    await session.commit()
    return chunk


async def test_list_for_thread_returns_messages_in_order_with_citations(db_session):
    user, thread = await _make_user_thread(db_session, "owner@example.com")
    chunk = await _make_chunk(db_session, user.id)
    await chat_messages.save_user_message(db_session, thread.id, "what drove growth?")
    await chat_messages.save_assistant_turn(
        db_session,
        thread.id,
        "data center demand",
        citations=[(chunk.id, "data center demand grew")],
    )

    messages = await chat_messages.list_for_thread(db_session, thread.id, user.id)

    assert [m.role for m in messages] == [MessageRole.user, MessageRole.assistant]
    assert messages[0].content == "what drove growth?"
    citations = messages[1].citations
    assert [(c.chunk_id, c.ordinal, c.quote) for c in citations] == [
        (chunk.id, 0, "data center demand grew")
    ]


async def test_list_for_thread_hides_foreign_users_threads(db_session):
    _, thread = await _make_user_thread(db_session, "owner@example.com")
    await chat_messages.save_user_message(db_session, thread.id, "secret question")

    assert await chat_messages.list_for_thread(db_session, thread.id, uuid.uuid4()) == []


async def test_save_user_message_persists_role_user(db_session):
    _, thread = await _make_user_thread(db_session, "user@example.com")

    message = await chat_messages.save_user_message(db_session, thread.id, "hi")

    assert message.role is MessageRole.user
    assert message.thread_id == thread.id
    assert message.id is not None
    assert message.created_at is not None


async def test_save_assistant_turn_writes_message_and_citations_in_one_transaction(
    db_session, session_factory
):
    user, thread = await _make_user_thread(db_session, "user@example.com")
    chunk_a = await _make_chunk(db_session, user.id)
    chunk_b = await _make_chunk(db_session, user.id)

    message = await chat_messages.save_assistant_turn(
        db_session,
        thread.id,
        "answer text",
        citations=[(chunk_a.id, "quote a"), (chunk_b.id, None)],
    )

    assert message.role is MessageRole.assistant
    assert message.content == "answer text"
    assert [(c.chunk_id, c.ordinal) for c in message.citations] == [
        (chunk_a.id, 0),
        (chunk_b.id, 1),
    ]

    # verify from a fresh session that the whole turn committed atomically
    async with session_factory() as check:
        reloaded = await chat_messages.list_for_thread(check, thread.id, user.id)
        assert [m.role for m in reloaded] == [MessageRole.assistant]
        assert [(c.chunk_id, c.ordinal, c.quote) for c in reloaded[0].citations] == [
            (chunk_a.id, 0, "quote a"),
            (chunk_b.id, 1, None),
        ]
