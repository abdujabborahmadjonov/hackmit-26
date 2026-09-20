"""Course plan request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.class_profile import ClassFormat
from app.taxonomy import EDUCATION_LEVELS, SUBJECTS, canonical_term

PlanStatus = Literal["draft", "active", "archived"]
ItemRole = Literal["core", "extension", "assessment"]

_EDUCATION_SET = set(EDUCATION_LEVELS)
_SUBJECT_SET = set(SUBJECTS)


class CoursePlanItemInput(BaseModel):
    role: ItemRole = "core"
    resource_id: uuid.UUID | None = None
    technique_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def require_link(self) -> CoursePlanItemInput:
        if self.resource_id is None and self.technique_id is None:
            raise ValueError("each item needs a resource_id and/or technique_id")
        return self


class CoursePlanSessionInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    focus: str | None = Field(default=None, max_length=4000)
    activities_summary: str | None = Field(default=None, max_length=8000)
    items: list[CoursePlanItemInput] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class CoursePlanUnitInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objectives: str | None = Field(default=None, max_length=8000)
    concept_labels: list[str] = Field(default_factory=list, max_length=30)
    sessions: list[CoursePlanSessionInput] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("concept_labels")
    @classmethod
    def clean_labels(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            label = value.strip()
            if label and label not in cleaned:
                cleaned.append(label[:120])
        return cleaned


class CoursePlanGenerateRequest(BaseModel):
    """Wizard inputs for generating a plan + planned class profile."""

    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=80)
    level: str = Field(min_length=1, max_length=50)
    format: ClassFormat = "lecture"
    duration_weeks: int = Field(ge=1, le=52)
    sessions_per_week: int = Field(default=1, ge=1, le=10)
    class_size: int | None = Field(default=None, gt=0, le=1000)
    class_size_min: int | None = Field(default=None, gt=0, le=1000)
    class_size_max: int | None = Field(default=None, gt=0, le=1000)
    class_length_minutes: int | None = Field(default=None, gt=0, le=600)
    goals: str | None = Field(default=None, max_length=8000)
    constraints: str | None = Field(default=None, max_length=4000)
    student_background: str | None = Field(default=None, max_length=4000)
    technology: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=4000)
    topic_hints: list[str] = Field(default_factory=list, max_length=40)
    # Optional: attach to an existing class instead of creating one.
    class_profile_id: uuid.UUID | None = None

    @field_validator("title", "subject", "level")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        slug = canonical_term(value)
        if slug not in _SUBJECT_SET:
            raise ValueError(
                f"subject must be one of the EduMatch taxonomy values "
                f"(got {value!r})"
            )
        return slug

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        slug = canonical_term(value)
        if slug not in _EDUCATION_SET:
            raise ValueError(
                f"level must be one of {sorted(_EDUCATION_SET)} (got {value!r})"
            )
        return slug

    @field_validator("topic_hints")
    @classmethod
    def clean_topics(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            label = value.strip()
            if label and label not in cleaned:
                cleaned.append(label[:120])
        return cleaned

    @model_validator(mode="after")
    def validate_size_range(self) -> CoursePlanGenerateRequest:
        if (
            self.class_size_min is not None
            and self.class_size_max is not None
            and self.class_size_min > self.class_size_max
        ):
            raise ValueError("class_size_min must be <= class_size_max")
        return self


class CoursePlanUpdate(BaseModel):
    """Metadata-only update (structure uses CoursePlanStructureUpdate)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: PlanStatus | None = None
    duration_weeks: int | None = Field(default=None, ge=1, le=52)
    sessions_per_week: int | None = Field(default=None, ge=1, le=10)
    goals: str | None = Field(default=None, max_length=8000)
    overview: str | None = Field(default=None, max_length=8000)
    constraints: str | None = Field(default=None, max_length=4000)


class CoursePlanStructureUpdate(BaseModel):
    """Replace the full unit/session/item tree (manual edit save)."""

    units: list[CoursePlanUnitInput] = Field(min_length=1)
    overview: str | None = Field(default=None, max_length=8000)


class CoursePlanRegenerateRequest(BaseModel):
    """Optional overrides when regenerating the whole plan."""

    duration_weeks: int | None = Field(default=None, ge=1, le=52)
    sessions_per_week: int | None = Field(default=None, ge=1, le=10)
    goals: str | None = Field(default=None, max_length=8000)
    constraints: str | None = Field(default=None, max_length=4000)
    topic_hints: list[str] | None = None


class CoursePlanItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    role: ItemRole
    resource_id: uuid.UUID | None = None
    technique_id: uuid.UUID | None = None
    resource_title: str | None = None
    technique_title: str | None = None


class CoursePlanSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    title: str
    focus: str | None = None
    activities_summary: str | None = None
    items: list[CoursePlanItemRead] = Field(default_factory=list)


class CoursePlanUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    title: str
    objectives: str | None = None
    concept_labels: list[str] = Field(default_factory=list)
    sessions: list[CoursePlanSessionRead] = Field(default_factory=list)


class CoursePlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    class_profile_id: uuid.UUID | None = None
    title: str
    subject: str
    level: str
    format: ClassFormat
    status: PlanStatus
    duration_weeks: int
    sessions_per_week: int
    goals: str | None = None
    overview: str | None = None
    unit_count: int = 0
    created_at: datetime
    updated_at: datetime


class CoursePlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    class_profile_id: uuid.UUID | None = None
    title: str
    subject: str
    level: str
    format: ClassFormat
    status: PlanStatus
    duration_weeks: int
    sessions_per_week: int
    goals: str | None = None
    overview: str | None = None
    constraints: str | None = None
    generation_inputs: dict[str, Any] = Field(default_factory=dict)
    similar_class_ids: list[str] = Field(default_factory=list)
    similar_classes: list[dict[str, Any]] = Field(default_factory=list)
    units: list[CoursePlanUnitRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CoursePlanGenerationFailure(BaseModel):
    """Returned when grounding coverage is too thin to cite resources."""

    cannot_generate: Literal[True] = True
    reason: str
    resource_candidates: int = 0
    technique_candidates: int = 0
    similar_classes: int = 0
