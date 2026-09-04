from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.database.models import MessageRole


class CreateThreadRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class ThreadPublic(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    question: str = Field(min_length=1)


class CitationPublic(BaseModel):
    chunk_id: UUID
    ordinal: int
    quote: str | None

    model_config = {"from_attributes": True}


class MessagePublic(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    created_at: datetime
    citations: list[CitationPublic]

    model_config = {"from_attributes": True}
