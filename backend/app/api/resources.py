"""Educational resource metadata, uploads and recommendations."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.resource import Resource
from app.schemas.common import Message
from app.schemas.resource import (
    ALLOWED_UPLOAD_TYPES,
    RecommendedResource,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
)
from app.schemas.search import ResourceSearchResponse, ResourceSearchResult
from app.services import elasticsearch_service as es
from app.services.embedding_service import EmbeddingError, get_embedding_service
from app.services.recommendation_service import ProfileRequiredError, RecommendationService
from app.services.search_service import ResourceSearchQuery, SearchService
from app.services.storage_service import StorageError, get_storage
from app.utils.auth import CurrentUser, OptionalUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resources", tags=["resources"])

DB = Annotated[AsyncSession, Depends(get_db)]


async def _embed_resource(resource: Resource) -> None:
    embeddings = get_embedding_service()
    text = embeddings.build_resource_text(
        title=resource.title,
        description=resource.description,
        subject=resource.subject,
        education_level=resource.education_level,
        teaching_method=resource.teaching_method,
        difficulty=resource.difficulty,
        tags=resource.tags,
    )
    try:
        resource.embedding = await embeddings.generate_embedding(text)
    except EmbeddingError as exc:
        logger.error("Resource embedding failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not generate the resource embedding: {exc}",
        ) from exc


async def _get_owned_resource(resource_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Resource:
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id))
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if resource.owner_id != user_id:
        # 403, not 404: the caller already knows the resource exists.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify resources you own",
        )
    return resource


@router.post(
    "",
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a resource (metadata only)",
    description="Use POST /resources/upload to attach a file in the same request.",
)
async def create_resource(payload: ResourceCreate, current_user: CurrentUser, db: DB) -> ResourceRead:
    resource = Resource(owner_id=current_user.id, **payload.model_dump())
    await _embed_resource(resource)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    await es.index_resource(resource)
    return ResourceRead.model_validate(resource)


@router.post(
    "/upload",
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file and create the resource",
    description=(
        f"Accepted file types: {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}. "
        "Maximum size is set by MAX_UPLOAD_SIZE_MB (default 25 MB)."
    ),
)
async def upload_resource(
    current_user: CurrentUser,
    db: DB,
    file: Annotated[UploadFile, File(description="The resource file")],
    title: Annotated[str, Form(min_length=3, max_length=250)],
    description: Annotated[str | None, Form()] = None,
    resource_type: Annotated[str | None, Form()] = None,
    subject: Annotated[str | None, Form()] = None,
    education_level: Annotated[str | None, Form()] = None,
    difficulty: Annotated[str | None, Form()] = None,
    teaching_method: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form(description="Comma separated")] = None,
) -> ResourceRead:
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{extension or 'unknown'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_TYPES))}",
        )

    data = await file.read(settings.max_upload_size_bytes + 1)
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB limit",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    # Trust the extension allow-list over the client-supplied content type.
    content_type = ALLOWED_UPLOAD_TYPES[extension]

    payload = ResourceCreate(
        title=title,
        description=description,
        resource_type=resource_type,
        subject=subject,
        education_level=education_level,
        difficulty=difficulty,
        teaching_method=teaching_method,
        tags=[tag.strip() for tag in (tags or "").split(",") if tag.strip()],
    )

    try:
        file_url = await get_storage().save(data, file.filename or "resource", content_type)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    resource = Resource(
        owner_id=current_user.id,
        **payload.model_dump(exclude={"file_url"}),
        file_url=file_url,
        file_name=os.path.basename(file.filename or "resource"),
        file_size_bytes=len(data),
        mime_type=content_type,
    )
    await _embed_resource(resource)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    await es.index_resource(resource)
    return ResourceRead.model_validate(resource)


@router.get(
    "",
    response_model=ResourceSearchResponse,
    summary="Browse and filter resources",
)
async def list_resources(
    db: DB,
    _: OptionalUser,
    query: Annotated[str | None, Query()] = None,
    subject: Annotated[str | None, Query()] = None,
    education_level: Annotated[str | None, Query()] = None,
    difficulty: Annotated[str | None, Query()] = None,
    teaching_method: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    sort: Annotated[str, Query(pattern="^(relevance|newest|popular)$")] = "newest",
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
            owner_id=owner_id,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )
    return ResourceSearchResponse(
        items=[
            ResourceSearchResult(resource=ResourceRead.model_validate(r), score=round(s, 4))
            for r, s in outcome.hits
        ],
        total=outcome.total,
        limit=limit,
        offset=offset,
        engine=outcome.engine,
        took_ms=outcome.took_ms,
    )


@router.get(
    "/recommended",
    response_model=list[RecommendedResource],
    summary="Resources picked for your profile",
    description=(
        "Blends semantic similarity to your teaching profile (40%) with subject "
        "(30%), education level (20%) and teaching method (10%) matches."
    ),
)
async def recommended_resources(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[RecommendedResource]:
    try:
        rows = await RecommendationService(db).recommend_resources(current_user.id, limit=limit)
    except ProfileRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [
        RecommendedResource(
            resource=ResourceRead.model_validate(resource),
            match_score=round(score, 4),
            reasons=reasons,
        )
        for resource, score, reasons in rows
    ]


@router.get("/{resource_id}", response_model=ResourceRead, summary="One resource")
async def get_resource(resource_id: uuid.UUID, db: DB, _: OptionalUser) -> ResourceRead:
    resource = await db.scalar(select(Resource).where(Resource.id == resource_id))
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    return ResourceRead.model_validate(resource)


@router.put("/{resource_id}", response_model=ResourceRead, summary="Update your resource")
async def update_resource(
    resource_id: uuid.UUID, payload: ResourceUpdate, current_user: CurrentUser, db: DB
) -> ResourceRead:
    resource = await _get_owned_resource(resource_id, current_user.id, db)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(resource, field, value)
    if updates.keys() & {
        "title",
        "description",
        "subject",
        "education_level",
        "teaching_method",
        "difficulty",
        "tags",
    }:
        await _embed_resource(resource)
    await db.commit()
    await db.refresh(resource)
    await es.index_resource(resource)
    return ResourceRead.model_validate(resource)


@router.delete("/{resource_id}", response_model=Message, summary="Delete your resource")
async def delete_resource(resource_id: uuid.UUID, current_user: CurrentUser, db: DB) -> Message:
    resource = await _get_owned_resource(resource_id, current_user.id, db)
    file_url = resource.file_url
    await db.delete(resource)
    await db.commit()
    await es.delete_resource(resource_id)
    if file_url:
        try:
            await get_storage().delete(file_url)
        except StorageError as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Could not delete stored file %s: %s", file_url, exc)
    return Message(detail="Resource deleted")
