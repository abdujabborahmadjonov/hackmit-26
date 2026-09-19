"""Messaging schemas.

Note: messages are encrypted in transit (HTTPS) and stored server-side.
EduMatch does not provide end-to-end encryption.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic


class MessageCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"content": "Loved your project-based Python unit - want to co-build one?"}
        }
    )

    content: str = Field(min_length=1, max_length=5000)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "participant_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "content": "Hi! Saw we both teach project-based CS.",
            }
        }
    )

    participant_id: uuid.UUID = Field(description="The other educator in the conversation")
    content: str | None = Field(
        default=None, max_length=5000, description="Optional first message"
    )


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    content: str
    created_at: datetime
    read_at: datetime | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    participants: list[UserPublic] = Field(default_factory=list)
    last_message: MessageRead | None = None
    unread_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
