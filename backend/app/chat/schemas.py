from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateThreadRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class ThreadPublic(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
