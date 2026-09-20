"""Resource metadata schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserPublic
from app.taxonomy import (
    DIFFICULTIES,
    EDUCATION_LEVELS,
    RESOURCE_TYPES,
    TEACHING_METHODS,
    canonical_term,
    slugify,
)

ALLOWED_UPLOAD_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ResourceBase(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    description: str | None = Field(default=None, max_length=4000)
    resource_type: str | None = None
    subject: str | None = None
    education_level: str | None = None
    difficulty: str | None = None
    teaching_method: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("resource_type")
    @classmethod
    def check_type(cls, v: str | None) -> str | None:
        if not v:
            return None
        slug = slugify(v)
        if slug not in RESOURCE_TYPES:
            raise ValueError(f"resource_type must be one of {RESOURCE_TYPES}")
        return slug

    @field_validator("education_level")
    @classmethod
    def check_level(cls, v: str | None) -> str | None:
        if not v:
            return None
        slug = slugify(v)
        if slug not in EDUCATION_LEVELS:
            raise ValueError(f"education_level must be one of {EDUCATION_LEVELS}")
        return slug

    @field_validator("difficulty")
    @classmethod
    def check_difficulty(cls, v: str | None) -> str | None:
        if not v:
            return None
        slug = slugify(v)
        if slug not in DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
        return slug

    @field_validator("teaching_method")
    @classmethod
    def check_method(cls, v: str | None) -> str | None:
        if not v:
            return None
        slug = slugify(v)
        if slug not in TEACHING_METHODS:
            raise ValueError(f"teaching_method must be one of {TEACHING_METHODS}")
        return slug

    @field_validator("subject")
    @classmethod
    def check_subject(cls, v: str | None) -> str | None:
        return canonical_term(v) if v else None

    @field_validator("tags")
    @classmethod
    def check_tags(cls, v: list[str] | None) -> list[str]:
        cleaned: list[str] = []
        for tag in v or []:
            term = canonical_term(tag)
            if term and term not in cleaned:
                cleaned.append(term)
        if len(cleaned) > 20:
            raise ValueError("At most 20 tags allowed")
        return cleaned


class ResourceCreate(ResourceBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Intro to Python Functions - Project Pack",
                "description": "A three-lesson project where students build a text adventure.",
                "resource_type": "project_brief",
                "subject": "computer_science",
                "education_level": "high_school",
                "difficulty": "beginner",
                "teaching_method": "project_based",
                "tags": ["python", "functions", "projects"],
            }
        }
    )

    file_url: str | None = Field(
        default=None,
        max_length=1000,
        description="Set automatically when uploading via POST /resources/upload",
    )


class ResourceUpdate(ResourceBase):
    """Partial update - unset fields are left untouched."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"difficulty": "intermediate", "tags": ["python", "oop"]}}
    )

    title: str | None = Field(default=None, min_length=3, max_length=250)
    tags: list[str] | None = None
    file_url: str | None = Field(default=None, max_length=1000)


class ResourceRead(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    owner: UserPublic | None = None
    file_url: str | None = None
    file_name: str | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = None
    download_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RecommendedResource(BaseModel):
    resource: ResourceRead
    match_score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
