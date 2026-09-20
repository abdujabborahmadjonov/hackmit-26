"""Discussion forum schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic

ForumCategory = Literal[
    "general",
    "collaboration",
    "curriculum",
    "classroom",
    "resources",
    "technology",
]

FORUM_CATEGORIES: tuple[str, ...] = (
    "general",
    "collaboration",
    "curriculum",
    "classroom",
    "resources",
    "technology",
)


class ForumTopicCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Anyone co-planning a project-based CS unit this term?",
                "body": "Looking for a partner to swap rubrics and peer-review student pitches.",
                "category": "collaboration",
            }
        }
    )

    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    category: ForumCategory = "general"


class ForumTopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    category: ForumCategory | None = None


class ForumPostCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"content": "Happy to swap rubrics — I teach AP CSP and run similar pitches."}
        }
    )

    content: str = Field(min_length=1, max_length=5000)


class ForumPostUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ForumPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    author_id: uuid.UUID
    author: UserPublic | None = None
    content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ForumTopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    author_id: uuid.UUID
    author: UserPublic | None = None
    title: str
    body: str
    category: str
    reply_count: int = 0
    last_activity_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
