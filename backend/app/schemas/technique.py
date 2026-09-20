"""Concept and technique schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.technique import PROBLEM_TYPES
from app.schemas.user import UserPublic

ProblemType = Literal[
    "misconception",
    "missing_prerequisite",
    "engagement",
    "pacing",
    "transfer",
]


class ConceptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    label: str
    subject: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ConceptChip(BaseModel):
    id: uuid.UUID | None = None
    label: str
    slug: str | None = None
    subject: str | None = None


class TechniqueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    summary: str = Field(min_length=1, max_length=8000)
    steps: str = Field(min_length=1, max_length=16000)
    materials: str | None = Field(default=None, max_length=4000)
    class_time_minutes: int | None = Field(default=None, gt=0, le=600)
    teaching_style: str | None = Field(default=None, max_length=80)
    context_subject: str | None = Field(default=None, max_length=80)
    context_level: str | None = Field(default=None, max_length=50)
    context_format: str | None = Field(default=None, max_length=20)
    context_class_size: int | None = Field(default=None, gt=0, le=1000)
    context_notes: str | None = Field(default=None, max_length=4000)
    problem_types: list[ProblemType] = Field(default_factory=list)
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    is_draft: bool = False
    is_published: bool = True

    @field_validator("problem_types")
    @classmethod
    def validate_problem_types(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in PROBLEM_TYPES]
        if unknown:
            raise ValueError(f"Unknown problem types: {', '.join(unknown)}")
        return list(dict.fromkeys(value))


class TechniqueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    summary: str | None = Field(default=None, min_length=1, max_length=8000)
    steps: str | None = Field(default=None, min_length=1, max_length=16000)
    materials: str | None = Field(default=None, max_length=4000)
    class_time_minutes: int | None = Field(default=None, gt=0, le=600)
    teaching_style: str | None = Field(default=None, max_length=80)
    context_subject: str | None = Field(default=None, max_length=80)
    context_level: str | None = Field(default=None, max_length=50)
    context_format: str | None = Field(default=None, max_length=20)
    context_class_size: int | None = Field(default=None, gt=0, le=1000)
    context_notes: str | None = Field(default=None, max_length=4000)
    problem_types: list[ProblemType] | None = None
    concept_ids: list[uuid.UUID] | None = None
    is_draft: bool | None = None
    is_published: bool | None = None


class TechniqueRatingSummary(BaseModel):
    average: float
    count: int
    distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Keys '1'..'5' -> counts",
    )
    similar_class_count: int = 0
    sample_comment: str | None = None


class TechniqueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    owner: UserPublic | None = None
    title: str
    summary: str
    steps: str
    materials: str | None = None
    class_time_minutes: int | None = None
    teaching_style: str | None = None
    context_subject: str | None = None
    context_level: str | None = None
    context_format: str | None = None
    context_class_size: int | None = None
    context_notes: str | None = None
    problem_types: list[str] = Field(default_factory=list)
    is_draft: bool
    is_published: bool
    average_rating: float
    rating_count: int
    concepts: list[ConceptRead] = Field(default_factory=list)
    rating_summary: TechniqueRatingSummary | None = None
    score: float | None = None
    score_breakdown: dict[str, float] | None = None
    created_at: datetime
    updated_at: datetime


class TechniqueDraft(BaseModel):
    """LLM-drafted technique from slides; teacher edits before saving."""

    title: str = ""
    summary: str = ""
    steps: str = ""
    materials: str | None = None
    class_time_minutes: int | None = None
    teaching_style: str | None = None
    problem_types: list[ProblemType] = Field(default_factory=list)
    concept_labels: list[str] = Field(default_factory=list)
    confidence: str = "low"


class TechniqueSearchParseRequest(BaseModel):
    class_profile_id: uuid.UUID
    concept_text: str = Field(min_length=1, max_length=500)
    problem_text: str = Field(min_length=1, max_length=2000)
    round: int = Field(default=0, ge=0, le=2)


class FollowUpOption(BaseModel):
    id: str
    label: str
    example: str | None = None


class TechniqueSearchParseResponse(BaseModel):
    concept_chips: list[ConceptChip]
    problem_chips: list[str]
    problem_types: list[ProblemType] = Field(default_factory=list)
    needs_follow_up: bool = False
    follow_up_kind: Literal["concept", "problem", "none"] = "none"
    follow_up_prompt: str | None = None
    follow_up_options: list[FollowUpOption] = Field(default_factory=list)
    vague_vs_specific: str | None = None
    round: int = 0


class TechniqueSearchRefineRequest(BaseModel):
    class_profile_id: uuid.UUID
    concept_chips: list[ConceptChip] = Field(default_factory=list)
    problem_chips: list[str] = Field(default_factory=list)
    problem_types: list[ProblemType] = Field(default_factory=list)
    selected_option_ids: list[str] = Field(default_factory=list)
    round: int = Field(default=1, ge=0, le=2)


class TechniqueSearchRunRequest(BaseModel):
    class_profile_id: uuid.UUID
    concept_ids: list[uuid.UUID] = Field(default_factory=list)
    concept_labels: list[str] = Field(default_factory=list)
    problem_types: list[ProblemType] = Field(default_factory=list)
    problem_text: str | None = Field(default=None, max_length=2000)
    limit: int = Field(default=10, ge=1, le=40)


class TechniqueSearchRunResponse(BaseModel):
    items: list[TechniqueRead]
    query_concepts: list[ConceptChip] = Field(default_factory=list)
    problem_types: list[ProblemType] = Field(default_factory=list)


class PitfallItem(BaseModel):
    problem_type: ProblemType
    label: str
    report_count: int
    top_techniques: list[TechniqueRead] = Field(default_factory=list)


class PlanningResponse(BaseModel):
    class_profile_id: uuid.UUID
    concept: ConceptChip | None = None
    pitfalls: list[PitfallItem] = Field(default_factory=list)


class RatingLinkCreate(BaseModel):
    class_profile_id: uuid.UUID | None = None
    label: str | None = Field(default=None, max_length=120)
    duration_minutes: int = Field(default=120, ge=15, le=60 * 24 * 14)
    max_uses: int | None = Field(default=None, ge=1, le=500)


class RatingLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    technique_id: uuid.UUID
    teacher_id: uuid.UUID
    class_profile_id: uuid.UUID | None = None
    label: str | None = None
    expires_at: datetime
    max_uses: int | None = None
    use_count: int
    is_revoked: bool
    is_active: bool = True
    created_at: datetime
    # Plaintext returned only on create.
    token: str | None = None
    rate_path: str | None = None


class TechniqueRatingCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class TechniqueRatingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    technique_id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime


class TriedThisRequest(BaseModel):
    class_profile_id: uuid.UUID
    label: str | None = Field(default=None, max_length=120)
    duration_minutes: int = Field(default=120, ge=15, le=60 * 24 * 14)
    max_uses: int | None = Field(default=40, ge=1, le=500)
