"""Rating + review schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserPublic


class RatingCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rating": 5,
                "comment": "Co-taught a robotics unit with her - brilliant at scaffolding projects.",
            }
        }
    )

    rating: int = Field(ge=1, le=5, description="1-5 stars")
    comment: str | None = Field(default=None, max_length=2000)


class RatingUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class RatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reviewer_id: uuid.UUID
    teacher_id: uuid.UUID
    reviewer: UserPublic | None = None
    rating: int
    comment: str | None = None
    is_verified_student: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RatingSummary(BaseModel):
    teacher_id: uuid.UUID
    average_rating: float
    rating_count: int
    distribution: dict[int, int] = Field(
        default_factory=dict, description="Star value -> number of ratings"
    )
