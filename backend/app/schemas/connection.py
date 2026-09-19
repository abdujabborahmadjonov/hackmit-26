"""Connection request schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.connection import ConnectionStatus
from app.schemas.user import UserPublic


class ConnectionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"receiver_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}}
    )

    receiver_id: uuid.UUID


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"status": "accepted"}})

    status: ConnectionStatus = Field(description="accepted | rejected | blocked")


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_id: uuid.UUID
    receiver_id: uuid.UUID
    status: ConnectionStatus
    requester: UserPublic | None = None
    receiver: UserPublic | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
