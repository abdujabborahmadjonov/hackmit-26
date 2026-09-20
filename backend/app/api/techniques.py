"""Technique cards, drafts, rating links, and anonymous student ratings."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.class_profile import ClassProfile
from app.models.technique import Technique, TechniqueConcept, TechniqueRating
from app.schemas.common import Message as MessageEnvelope
from app.schemas.common import Page
from app.schemas.technique import (
    ConceptRead,
    RatingLinkCreate,
    RatingLinkRead,
    TechniqueCreate,
    TechniqueDraft,
    TechniqueRatingCreate,
    TechniqueRatingRead,
    TechniqueRatingSummary,
    TechniqueRead,
    TechniqueUpdate,
    TriedThisRequest,
)
from app.schemas.user import UserPublic
from app.services import llm_service, rating_link_service
from app.services.llm_service import LLMUnavailable
from app.services.technique_search_service import (
    load_ratings_for,
    rating_summary_for,
    refresh_technique_embedding,
    recompute_technique_rating_aggregates,
)
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["techniques"])
DB = Annotated[AsyncSession, Depends(get_db)]
ai_rate_limit = RateLimiter("ai", 20)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
PDF_EXTENSIONS = {".pdf"}
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


def _technique_read(
    tech: Technique,
    *,
    ratings: list[TechniqueRating] | None = None,
    searcher: ClassProfile | None = None,
    score: float | None = None,
    breakdown: dict[str, float] | None = None,
) -> TechniqueRead:
    concepts = []
    for link in tech.concepts or []:
        if link.concept is not None:
            concepts.append(ConceptRead.model_validate(link.concept))
    summary = None
    if ratings is not None:
        summary = TechniqueRatingSummary(**rating_summary_for(ratings, searcher=searcher))
    return TechniqueRead(
        id=tech.id,
        owner_id=tech.owner_id,
        owner=UserPublic.model_validate(tech.owner) if tech.owner else None,
        title=tech.title,
        summary=tech.summary,
        steps=tech.steps,
        materials=tech.materials,
        class_time_minutes=tech.class_time_minutes,
        teaching_style=tech.teaching_style,
        context_subject=tech.context_subject,
        context_level=tech.context_level,
        context_format=tech.context_format,
        context_class_size=tech.context_class_size,
        context_notes=tech.context_notes,
        problem_types=list(tech.problem_types or []),
        is_draft=tech.is_draft,
        is_published=tech.is_published,
        average_rating=tech.average_rating,
        rating_count=tech.rating_count,
        concepts=concepts,
        rating_summary=summary,
        score=score,
        score_breakdown=breakdown,
        created_at=tech.created_at,
        updated_at=tech.updated_at,
    )


async def _get_technique(db: AsyncSession, technique_id: uuid.UUID) -> Technique:
    tech = await db.scalar(
        select(Technique)
        .where(Technique.id == technique_id)
        .options(selectinload(Technique.concepts).selectinload(TechniqueConcept.concept))
    )
    if tech is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technique not found")
    return tech


async def _set_concepts(
    db: AsyncSession, technique: Technique, concept_ids: list[uuid.UUID]
) -> None:
    await db.execute(delete(TechniqueConcept).where(TechniqueConcept.technique_id == technique.id))
    for cid in dict.fromkeys(concept_ids):
        db.add(TechniqueConcept(technique_id=technique.id, concept_id=cid))
    await db.flush()


@router.get("/techniques", response_model=Page[TechniqueRead])
async def list_techniques(
    current_user: CurrentUser,
    db: DB,
    mine: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TechniqueRead]:
    query = (
        select(Technique)
        .where(Technique.is_published.is_(True), Technique.is_draft.is_(False))
        .options(selectinload(Technique.concepts).selectinload(TechniqueConcept.concept))
    )
    if mine:
        query = select(Technique).where(Technique.owner_id == current_user.id).options(
            selectinload(Technique.concepts).selectinload(TechniqueConcept.concept)
        )
    rows = (
        await db.scalars(query.order_by(Technique.updated_at.desc()).limit(limit).offset(offset))
    ).all()
    ratings_map = await load_ratings_for(db, [r.id for r in rows])
    items = [_technique_read(r, ratings=ratings_map.get(r.id, [])) for r in rows]
    return Page(items=items, total=len(items), limit=limit, offset=offset)


@router.post(
    "/techniques",
    response_model=TechniqueRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_technique(
    payload: TechniqueCreate, current_user: CurrentUser, db: DB
) -> TechniqueRead:
    data = payload.model_dump(exclude={"concept_ids"})
    tech = Technique(owner_id=current_user.id, **data)
    db.add(tech)
    await db.flush()
    if payload.concept_ids:
        await _set_concepts(db, tech, payload.concept_ids)
    await refresh_technique_embedding(db, tech)
    await db.commit()
    tech = await _get_technique(db, tech.id)
    return _technique_read(tech, ratings=[])


@router.get("/techniques/{technique_id}", response_model=TechniqueRead)
async def get_technique(
    technique_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> TechniqueRead:
    del current_user
    tech = await _get_technique(db, technique_id)
    ratings = (await load_ratings_for(db, [tech.id])).get(tech.id, [])
    return _technique_read(tech, ratings=ratings)


@router.put("/techniques/{technique_id}", response_model=TechniqueRead)
async def update_technique(
    technique_id: uuid.UUID,
    payload: TechniqueUpdate,
    current_user: CurrentUser,
    db: DB,
) -> TechniqueRead:
    tech = await _get_technique(db, technique_id)
    if tech.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your technique")
    data = payload.model_dump(exclude_unset=True, exclude={"concept_ids"})
    for key, value in data.items():
        setattr(tech, key, value)
    if payload.concept_ids is not None:
        await _set_concepts(db, tech, payload.concept_ids)
    await refresh_technique_embedding(db, tech)
    await db.commit()
    tech = await _get_technique(db, technique_id)
    ratings = (await load_ratings_for(db, [tech.id])).get(tech.id, [])
    return _technique_read(tech, ratings=ratings)


@router.delete("/techniques/{technique_id}", response_model=MessageEnvelope)
async def delete_technique(
    technique_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    tech = await _get_technique(db, technique_id)
    if tech.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your technique")
    await db.delete(tech)
    await db.commit()
    return MessageEnvelope(detail="Technique deleted")


@router.post(
    "/techniques/from-document",
    response_model=TechniqueDraft,
    dependencies=[Depends(ai_rate_limit)],
)
async def technique_from_document(
    current_user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
) -> TechniqueDraft:
    del current_user
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    if file is None and not (text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attach a document or paste some text.",
        )

    pdf_bytes: bytes | None = None
    document_text: str | None = text
    if file is not None:
        source_name = os.path.basename(file.filename or "document")
        extension = os.path.splitext(source_name)[1].lower()
        if extension not in TEXT_EXTENSIONS | PDF_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Upload a PDF, TXT or Markdown file.",
            )
        data = await file.read(MAX_DOCUMENT_BYTES + 1)
        if len(data) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Documents are limited to 8 MB.",
            )
        if extension in PDF_EXTENSIONS:
            pdf_bytes = data
        else:
            document_text = data.decode("utf-8", errors="replace")

    try:
        drafted = await llm_service.draft_technique_from_document(
            document_text, pdf=pdf_bytes
        )
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return TechniqueDraft(
        title=drafted.title,
        summary=drafted.summary,
        steps=drafted.steps,
        materials=drafted.materials or None,
        class_time_minutes=drafted.class_time_minutes,
        teaching_style=drafted.teaching_style or None,
        problem_types=[p for p in drafted.problem_types if p in {
            "misconception", "missing_prerequisite", "engagement", "pacing", "transfer"
        }],  # type: ignore[list-item]
        concept_labels=drafted.concept_labels,
        confidence=drafted.confidence,
    )


@router.post(
    "/techniques/{technique_id}/tried-this",
    response_model=RatingLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def tried_this(
    technique_id: uuid.UUID,
    payload: TriedThisRequest,
    current_user: CurrentUser,
    db: DB,
) -> RatingLinkRead:
    tech = await _get_technique(db, technique_id)
    klass = await db.scalar(
        select(ClassProfile).where(
            ClassProfile.id == payload.class_profile_id,
            ClassProfile.teacher_id == current_user.id,
        )
    )
    if klass is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class profile not found")

    link, token = await rating_link_service.create_rating_link(
        db,
        technique_id=tech.id,
        teacher_id=current_user.id,
        class_profile_id=klass.id,
        duration_minutes=payload.duration_minutes,
        label=payload.label or f"Tried: {tech.title[:80]}",
        max_uses=payload.max_uses,
    )
    await db.commit()
    await db.refresh(link)
    return RatingLinkRead(**rating_link_service.link_to_read_fields(link, token=token))


@router.post(
    "/techniques/{technique_id}/rating-links",
    response_model=RatingLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_rating_link(
    technique_id: uuid.UUID,
    payload: RatingLinkCreate,
    current_user: CurrentUser,
    db: DB,
) -> RatingLinkRead:
    tech = await _get_technique(db, technique_id)
    if tech.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your technique")
    if payload.class_profile_id:
        klass = await db.scalar(
            select(ClassProfile).where(
                ClassProfile.id == payload.class_profile_id,
                ClassProfile.teacher_id == current_user.id,
            )
        )
        if klass is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Class profile not found"
            )
    link, token = await rating_link_service.create_rating_link(
        db,
        technique_id=tech.id,
        teacher_id=current_user.id,
        class_profile_id=payload.class_profile_id,
        duration_minutes=payload.duration_minutes,
        label=payload.label,
        max_uses=payload.max_uses,
    )
    await db.commit()
    await db.refresh(link)
    return RatingLinkRead(**rating_link_service.link_to_read_fields(link, token=token))


@router.get("/rate/{token}", response_model=TechniqueRead, summary="Preview technique for rating")
async def preview_rate(token: str, db: DB) -> TechniqueRead:
    link = await rating_link_service.get_active_link_by_token(db, token)
    tech = await _get_technique(db, link.technique_id)
    ratings = (await load_ratings_for(db, [tech.id])).get(tech.id, [])
    return _technique_read(tech, ratings=ratings)


@router.post(
    "/rate/{token}",
    response_model=TechniqueRatingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Anonymous student rating (no account, no PII)",
)
async def submit_rate(
    token: str, payload: TechniqueRatingCreate, db: DB
) -> TechniqueRatingRead:
    link = await rating_link_service.get_active_link_by_token(db, token)
    klass = None
    if link.class_profile_id:
        klass = await db.scalar(
            select(ClassProfile).where(ClassProfile.id == link.class_profile_id)
        )

    rating = TechniqueRating(
        technique_id=link.technique_id,
        class_profile_id=link.class_profile_id,
        rating_link_id=link.id,
        rating=payload.rating,
        comment=(payload.comment or "").strip() or None,
        context_subject=klass.subject if klass else None,
        context_level=klass.level if klass else None,
        context_format=klass.format if klass else None,
        context_class_size=int(klass.effective_class_size() or 0) or None if klass else None,
    )
    db.add(rating)
    await rating_link_service.consume_link(db, link)
    await db.flush()
    await recompute_technique_rating_aggregates(db, link.technique_id)
    await db.commit()
    await db.refresh(rating)
    return TechniqueRatingRead.model_validate(rating)
