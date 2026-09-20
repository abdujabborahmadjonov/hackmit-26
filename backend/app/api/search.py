"""Search across educators and resources (Postgres or Elasticsearch engine)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.profile import profile_summary
from app.schemas.resource import ResourceRead
from app.schemas.search import (
    ResourceSearchResponse,
    ResourceSearchResult,
    TeacherSearchResponse,
    TeacherSearchResult,
)
from app.services.search_service import (
    ResourceSearchQuery,
    SearchService,
    TeacherSearchQuery,
)
from app.utils.auth import OptionalUser
from app.utils.rate_limit import default_rate_limit

router = APIRouter(
    prefix="/search", tags=["search"], dependencies=[Depends(default_rate_limit)]
)

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/teachers",
    response_model=TeacherSearchResponse,
    summary="Search educators",
    description=(
        "Structured filters are applied in the database; `query` additionally "
        "runs a semantic (vector) + lexical search. Supply `latitude`, "
        "`longitude` and `radius_km` for geographic search."
    ),
)
async def search_teachers(
    db: DB,
    current_user: OptionalUser,
    query: Annotated[str | None, Query(description="Free text, matched semantically and lexically")] = None,
    subject: Annotated[str | None, Query(description="e.g. computer_science")] = None,
    education_level: Annotated[str | None, Query(description="e.g. high_school")] = None,
    teaching_level: Annotated[str | None, Query(description="beginner | intermediate | advanced")] = None,
    teaching_method: Annotated[str | None, Query(description="e.g. project_based")] = None,
    teaching_style: Annotated[str | None, Query(description="Free text or a method slug")] = None,
    location: Annotated[str | None, Query(description="City/region name")] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Query(gt=0, le=20000)] = None,
    minimum_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    class_size: Annotated[int | None, Query(gt=0, le=1000)] = None,
    language: Annotated[str | None, Query()] = None,
    institution_type: Annotated[str | None, Query()] = None,
    min_years_experience: Annotated[int | None, Query(ge=0, le=70)] = None,
    sort: Annotated[str, Query(pattern="^(relevance|rating|experience|distance|newest)$")] = "relevance",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    exclude_self: Annotated[bool, Query(description="Leave yourself out of the results")] = True,
) -> TeacherSearchResponse:
    search_query = TeacherSearchQuery(
        query=query,
        subject=subject,
        education_level=education_level,
        teaching_level=teaching_level,
        teaching_method=teaching_method,
        teaching_style=teaching_style,
        location=location,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        minimum_rating=minimum_rating,
        class_size=class_size,
        language=language,
        institution_type=institution_type,
        min_years_experience=min_years_experience,
        sort=sort,
        limit=limit,
        offset=offset,
        exclude_user_id=current_user.id if (current_user and exclude_self) else None,
    )
    outcome = await SearchService(db).search_teachers(search_query)
    return TeacherSearchResponse(
        items=[
            TeacherSearchResult(
                teacher=profile_summary(hit.profile, hit.user, hit.distance_km),
                score=round(hit.score, 4),
                distance_km=round(hit.distance_km, 1) if hit.distance_km is not None else None,
            )
            for hit in outcome.hits
        ],
        total=outcome.total,
        limit=limit,
        offset=offset,
        engine=outcome.engine,
        took_ms=outcome.took_ms,
    )


@router.get(
    "/resources",
    response_model=ResourceSearchResponse,
    summary="Search teaching resources",
)
async def search_resources(
    db: DB,
    _: OptionalUser,
    query: Annotated[str | None, Query()] = None,
    subject: Annotated[str | None, Query()] = None,
    education_level: Annotated[str | None, Query()] = None,
    difficulty: Annotated[str | None, Query()] = None,
    teaching_method: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    tags: Annotated[list[str] | None, Query(description="Repeat the parameter for multiple tags")] = None,
    sort: Annotated[str, Query(pattern="^(relevance|newest|popular)$")] = "relevance",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ResourceSearchResponse:
    outcome = await SearchService(db).search_resources(
        ResourceSearchQuery(
            query=query,
            subject=subject,
            education_level=education_level,
            difficulty=difficulty,
            teaching_method=teaching_method,
            resource_type=resource_type,
            tags=tags or [],
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )
    return ResourceSearchResponse(
        items=[
            ResourceSearchResult(resource=ResourceRead.model_validate(resource), score=round(score, 4))
            for resource, score in outcome.hits
        ],
        total=outcome.total,
        limit=limit,
        offset=offset,
        engine=outcome.engine,
        took_ms=outcome.took_ms,
    )


@router.get(
    "/engine",
    summary="Which search engine is active",
    description="Useful for demos: reports the configured engine and its health.",
)
async def search_engine_status() -> dict:
    status_payload: dict = {"provider": settings.search_provider}
    if settings.search_provider == "elasticsearch":
        from app.services import elasticsearch_service as es

        status_payload["elasticsearch_url"] = settings.elasticsearch_url
        status_payload["reachable"] = await es.ping()
        status_payload["fallback_to_postgres"] = settings.search_fallback_to_postgres
    return status_payload
