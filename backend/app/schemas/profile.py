"""Teacher profile schemas, including the vocabulary normalisation rules."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserPublic
from app.taxonomy import (
    EDUCATION_LEVELS,
    INSTITUTION_TYPES,
    TEACHING_LEVELS,
    TEACHING_METHODS,
    canonical_term,
    slugify,
)

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]

PROFILE_EXAMPLE: dict[str, Any] = {
    "bio": "I teach computer science using project-based learning.",
    "location_name": "Cambridge, Massachusetts",
    "latitude": 42.3736,
    "longitude": -71.1097,
    "education_levels": ["high_school"],
    "subjects": ["computer_science", "python", "artificial_intelligence"],
    "fields_of_expertise": ["machine_learning", "software_engineering"],
    "teaching_levels": ["beginner", "intermediate"],
    "teaching_methods": ["project_based", "collaborative"],
    "teaching_style": "Project-based, collaborative and hands-on.",
    "class_size": 25,
    "years_experience": 5,
    "languages": ["English"],
    "institution": "Cambridge Rindge and Latin School",
    "institution_type": "public_school",
}


def _normalise_enum_list(values: list[str] | None, allowed: list[str], field: str) -> list[str]:
    if values is None:
        return []
    cleaned: list[str] = []
    for value in values:
        slug = slugify(value)
        if slug not in allowed:
            raise ValueError(f"{field}: '{value}' is not one of {allowed}")
        if slug not in cleaned:
            cleaned.append(slug)
    return cleaned


def _normalise_free_list(values: list[str] | None, limit: int = 30) -> list[str]:
    if values is None:
        return []
    cleaned: list[str] = []
    for value in values:
        term = canonical_term(value)
        if term and term not in cleaned:
            cleaned.append(term)
    if len(cleaned) > limit:
        raise ValueError(f"At most {limit} entries allowed")
    return cleaned


class ProfileBase(BaseModel):
    bio: str | None = Field(default=None, max_length=4000)
    location_name: str | None = Field(
        default=None,
        max_length=200,
        description="City / region only. Do not submit a street address.",
    )
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    education_levels: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    fields_of_expertise: list[str] = Field(default_factory=list)

    teaching_levels: list[str] = Field(default_factory=list)
    teaching_methods: list[str] = Field(default_factory=list)
    teaching_style: str | None = Field(default=None, max_length=2000)
    class_size: int | None = Field(default=None, gt=0, le=1000)
    years_experience: int | None = Field(default=None, ge=0, le=70)

    languages: list[str] = Field(default_factory=list)
    institution: str | None = Field(default=None, max_length=200)
    institution_type: str | None = Field(default=None)

    @field_validator("education_levels")
    @classmethod
    def check_education_levels(cls, v: list[str] | None) -> list[str]:
        return _normalise_enum_list(v, EDUCATION_LEVELS, "education_levels")

    @field_validator("teaching_levels")
    @classmethod
    def check_teaching_levels(cls, v: list[str] | None) -> list[str]:
        return _normalise_enum_list(v, TEACHING_LEVELS, "teaching_levels")

    @field_validator("teaching_methods")
    @classmethod
    def check_teaching_methods(cls, v: list[str] | None) -> list[str]:
        return _normalise_enum_list(v, TEACHING_METHODS, "teaching_methods")

    @field_validator("subjects", "fields_of_expertise")
    @classmethod
    def check_terms(cls, v: list[str] | None) -> list[str]:
        return _normalise_free_list(v)

    @field_validator("languages")
    @classmethod
    def check_languages(cls, v: list[str] | None) -> list[str]:
        return [lang.strip() for lang in (v or []) if lang and lang.strip()][:15]

    @field_validator("institution_type")
    @classmethod
    def check_institution_type(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        slug = slugify(v)
        if slug not in INSTITUTION_TYPES:
            raise ValueError(f"institution_type must be one of {INSTITUTION_TYPES}")
        return slug

    @field_validator("latitude", "longitude")
    @classmethod
    def round_coordinates(cls, v: float | None) -> float | None:
        # ~1 km precision: enough for proximity matching, coarse enough that we
        # are not storing anyone's home address.
        return None if v is None else round(v, 2)


class ProfileCreate(ProfileBase):
    model_config = ConfigDict(json_schema_extra={"example": PROFILE_EXAMPLE})


class ProfileUpdate(ProfileBase):
    """Partial update - only the fields present in the body are applied."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"class_size": 28, "teaching_style": "Flipped classroom."}}
    )

    education_levels: list[str] | None = None
    subjects: list[str] | None = None
    fields_of_expertise: list[str] | None = None
    teaching_levels: list[str] | None = None
    teaching_methods: list[str] | None = None
    languages: list[str] | None = None


class ProfileRead(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user: UserPublic | None = None
    average_rating: float = 0.0
    rating_count: int = 0
    has_embedding: bool = Field(
        default=False, description="Whether a semantic vector has been generated"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, profile, *, user=None) -> "ProfileRead":
        data = cls.model_validate(profile)
        data.has_embedding = profile.teaching_style_embedding is not None
        if user is not None:
            data.user = UserPublic.model_validate(user)
        return data


class ProfileSummary(BaseModel):
    """Compact profile used inside search results and recommendations."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    first_name: str
    last_name: str
    profile_photo_url: str | None = None
    bio: str | None = None
    location_name: str | None = None
    education_levels: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    fields_of_expertise: list[str] = Field(default_factory=list)
    teaching_levels: list[str] = Field(default_factory=list)
    teaching_methods: list[str] = Field(default_factory=list)
    teaching_style: str | None = None
    class_size: int | None = None
    years_experience: int | None = None
    languages: list[str] = Field(default_factory=list)
    institution: str | None = None
    institution_type: str | None = None
    average_rating: float = 0.0
    rating_count: int = 0
    distance_km: float | None = None


def profile_summary(profile, user, distance_km: float | None = None) -> ProfileSummary:
    """Build the compact card used by search results and recommendations."""
    return ProfileSummary(
        user_id=profile.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        profile_photo_url=user.profile_photo_url,
        bio=profile.bio,
        location_name=profile.location_name,
        education_levels=list(profile.education_levels or []),
        subjects=list(profile.subjects or []),
        fields_of_expertise=list(profile.fields_of_expertise or []),
        teaching_levels=list(profile.teaching_levels or []),
        teaching_methods=list(profile.teaching_methods or []),
        teaching_style=profile.teaching_style,
        class_size=profile.class_size,
        years_experience=profile.years_experience,
        languages=list(profile.languages or []),
        institution=profile.institution,
        institution_type=profile.institution_type,
        average_rating=profile.average_rating,
        rating_count=profile.rating_count,
        distance_km=round(distance_km, 1) if distance_km is not None else None,
    )
