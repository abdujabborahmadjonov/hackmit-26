"""Class profile schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLASS_FORMATS = ("lecture", "lab", "online", "hybrid")
CLASS_STATUSES = ("planned", "active", "archived")

ClassFormat = Literal["lecture", "lab", "online", "hybrid"]
ClassStatus = Literal["planned", "active", "archived"]


class ClassProfileBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=80)
    level: str = Field(min_length=1, max_length=50)
    format: ClassFormat
    status: ClassStatus = "planned"
    class_size: int | None = Field(default=None, gt=0, le=1000)
    class_size_min: int | None = Field(default=None, gt=0, le=1000)
    class_size_max: int | None = Field(default=None, gt=0, le=1000)
    student_background: str | None = Field(default=None, max_length=4000)
    constraints: str | None = Field(default=None, max_length=4000)
    class_length_minutes: int | None = Field(default=None, gt=0, le=600)
    technology: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("subject", "level", "title")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_size_range(self) -> ClassProfileBase:
        if (
            self.class_size_min is not None
            and self.class_size_max is not None
            and self.class_size_min > self.class_size_max
        ):
            raise ValueError("class_size_min must be <= class_size_max")
        if self.status == "planned":
            return self
        # Active/archived prefer a concrete size when ranges were used.
        if self.class_size is None and (
            self.class_size_min is not None or self.class_size_max is not None
        ):
            # Allow promote endpoint to set concrete size; create can still send range.
            pass
        return self


class ClassProfileCreate(ClassProfileBase):
    pass


class ClassProfileUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, min_length=1, max_length=80)
    level: str | None = Field(default=None, min_length=1, max_length=50)
    format: ClassFormat | None = None
    status: ClassStatus | None = None
    class_size: int | None = Field(default=None, gt=0, le=1000)
    class_size_min: int | None = Field(default=None, gt=0, le=1000)
    class_size_max: int | None = Field(default=None, gt=0, le=1000)
    student_background: str | None = Field(default=None, max_length=4000)
    constraints: str | None = Field(default=None, max_length=4000)
    class_length_minutes: int | None = Field(default=None, gt=0, le=600)
    technology: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=4000)


class ClassProfilePromote(BaseModel):
    """Promote a planned profile to active with concrete values."""

    class_size: int = Field(gt=0, le=1000)
    format: ClassFormat | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ClassProfileRead(ClassProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ClassProfileDraft(BaseModel):
    """Syllabus-extracted draft; nothing is saved until the teacher confirms."""

    title: str | None = None
    subject: str | None = None
    level: str | None = None
    format: ClassFormat | None = None
    class_size: int | None = None
    class_size_min: int | None = None
    class_size_max: int | None = None
    student_background: str | None = None
    constraints: str | None = None
    class_length_minutes: int | None = None
    technology: str | None = None
    notes: str | None = None
    confidence: str = "low"
