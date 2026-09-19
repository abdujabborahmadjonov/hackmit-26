"""User-facing account schemas. `password_hash` is never exposed."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPublic(BaseModel):
    """What other educators can see about an account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    profile_photo_url: str | None = None
    is_verified: bool = False
    created_at: datetime | None = None


class UserPrivate(UserPublic):
    """The authenticated user's own account record."""

    model_config = ConfigDict(from_attributes=True)

    email: EmailStr
    updated_at: datetime | None = None


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    profile_photo_url: str | None = Field(default=None, max_length=500)
