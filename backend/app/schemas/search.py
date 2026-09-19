"""Search request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import ProfileSummary
from app.schemas.resource import ResourceRead


class TeacherSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    teacher: ProfileSummary
    score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Relevance within this result set - use it to rank, not as an absolute "
            "quality measure. 1.0 when no free-text query was supplied."
        ),
    )
    distance_km: float | None = None
    highlights: list[str] = Field(default_factory=list)


class TeacherSearchResponse(BaseModel):
    items: list[TeacherSearchResult]
    total: int
    limit: int
    offset: int
    engine: str = Field(description="postgres | elasticsearch")
    took_ms: float


class ResourceSearchResult(BaseModel):
    resource: ResourceRead
    score: float = Field(ge=0.0, le=1.0)


class ResourceSearchResponse(BaseModel):
    items: list[ResourceSearchResult]
    total: int
    limit: int
    offset: int
    engine: str
    took_ms: float
