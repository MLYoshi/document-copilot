# Import every model module so SQLAlchemy registers all tables on Base.metadata.
# Alembic env.py imports this package for autogenerate support.
from app.database.models.chat_message import ChatMessage, MessageRole
from app.database.models.chat_thread import ChatThread
from app.database.models.document_chunk import DocumentChunk
from app.database.models.message_citation import MessageCitation
from app.database.models.refresh_token import RefreshToken
from app.database.models.source_document import DocumentStatus, SourceDocument
from app.database.models.user import User

__all__ = [
    "ChatMessage",
    "ChatThread",
    "DocumentChunk",
    "DocumentStatus",
    "MessageCitation",
    "MessageRole",
    "RefreshToken",
    "SourceDocument",
    "User",
]
