"""Student-verified rating schemas and classroom verification tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.user import UserPublic


class RatingCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "verification_token": "K7MP-9Q2R",
                "knowledge_of_material": 5,
                "presentation": 4,
                "friendliness": 5,
                "other": 4,
                "comment": "Clear explanations and very approachable after class.",
            }
        }
    )

    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Overall 1-5 stars. Optional when aspect scores are provided "
        "(overall is then the rounded average of the aspects).",
    )
    knowledge_of_material: int | None = Field(default=None, ge=1, le=5)
    presentation: int | None = Field(default=None, ge=1, le=5)
    friendliness: int | None = Field(default=None, ge=1, le=5)
    other: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    verification_token: str | None = Field(
        default=None,
        max_length=64,
        description="Classroom code from the educator. Required for verified student ratings.",
    )

    @model_validator(mode="after")
    def require_score_or_aspects(self) -> RatingCreate:
        aspects = (
            self.knowledge_of_material,
            self.presentation,
            self.friendliness,
            self.other,
        )
        has_any_aspect = any(value is not None for value in aspects)
        has_all_aspects = all(value is not None for value in aspects)

        if self.verification_token:
            if not has_all_aspects:
                raise ValueError(
                    "Verified student ratings require knowledge_of_material, "
                    "presentation, friendliness, and other scores"
                )
        elif self.rating is None and not has_all_aspects:
            raise ValueError("Provide an overall rating or all four aspect scores")

        if has_any_aspect and not has_all_aspects:
            raise ValueError(
                "When rating aspects, provide all of: knowledge_of_material, "
                "presentation, friendliness, and other"
            )
        return self


class RatingUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    knowledge_of_material: int | None = Field(default=None, ge=1, le=5)
    presentation: int | None = Field(default=None, ge=1, le=5)
    friendliness: int | None = Field(default=None, ge=1, le=5)
    other: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class RatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reviewer_id: uuid.UUID
    teacher_id: uuid.UUID
    reviewer: UserPublic | None = None
    rating: int
    knowledge_of_material: int | None = None
    presentation: int | None = None
    friendliness: int | None = None
    other: int | None = None
    comment: str | None = None
    is_verified_student: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AspectAverages(BaseModel):
    knowledge_of_material: float | None = None
    presentation: float | None = None
    friendliness: float | None = None
    other: float | None = None


class RatingSummary(BaseModel):
    teacher_id: uuid.UUID
    average_rating: float
    rating_count: int
    verified_student_count: int = 0
    distribution: dict[int, int] = Field(
        default_factory=dict, description="Star value -> number of ratings"
    )
    aspect_averages: AspectAverages = Field(default_factory=AspectAverages)


class StudentTokenCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "duration_minutes": 120,
                "label": "Period 3 Biology — Friday",
                "max_uses": 35,
            }
        }
    )

    duration_minutes: int = Field(
        ge=5,
        le=60 * 24 * 30,
        description="How long the token stays valid, from 5 minutes up to 30 days.",
    )
    label: str | None = Field(default=None, max_length=120)
    max_uses: int | None = Field(
        default=None,
        ge=1,
        le=10_000,
        description="Optional cap on redemptions. Omit for unlimited uses until expiry.",
    )


class StudentTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    label: str | None = None
    expires_at: datetime
    max_uses: int | None = None
    use_count: int
    is_revoked: bool
    is_active: bool = False
    created_at: datetime | None = None


class StudentTokenCreated(StudentTokenRead):
    """Returned only at creation time — includes the plaintext classroom code."""

    token: str = Field(description="Share this code with students. It is not shown again.")
