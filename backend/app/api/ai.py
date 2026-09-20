"""Generative endpoints: the collaboration brief and syllabus import.

Both are additive. Without LLM_API_KEY they return 503 with a clear message
and the rest of the product is unaffected.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import TeacherProfile
from app.models.resource import Resource
from app.models.user import User
from app.services import llm_service
from app.services.llm_service import LLMUnavailable
from app.services.recommendation_service import score_profiles
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

DB = Annotated[AsyncSession, Depends(get_db)]

# Generation is the one expensive call in this API - a tighter limit than the
# default, and a short cache so a demo clicking the same match repeatedly does
# not pay for it twice.
ai_rate_limit = RateLimiter("ai", 20)
_BRIEF_CACHE: dict[tuple[uuid.UUID, uuid.UUID], tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 15 * 60

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
PDF_EXTENSIONS = {".pdf"}
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


class BriefResponse(BaseModel):
    brief: str = Field(description="A short, concrete proposal for working together")
    teacher_id: uuid.UUID
    cached: bool = False


class ProfileDraft(BaseModel):
    """A suggested profile. Nothing is saved - the teacher reviews and submits."""

    subjects: list[str] = Field(default_factory=list)
    education_levels: list[str] = Field(default_factory=list)
    teaching_levels: list[str] = Field(default_factory=list)
    teaching_methods: list[str] = Field(default_factory=list)
    fields_of_expertise: list[str] = Field(default_factory=list)
    teaching_style: str = ""
    class_size: int | None = None
    confidence: str = "low"
    source_name: str | None = None


class AIStatus(BaseModel):
    enabled: bool
    features: list[str]


@router.get("/status", response_model=AIStatus, summary="Are the generative features on?")
async def ai_status() -> AIStatus:
    """Lets the client hide buttons that would only 503."""
    return AIStatus(
        enabled=llm_service.is_enabled(),
        features=(
            [
                "collaboration_brief",
                "profile_import",
                "class_import",
                "technique_draft",
                "technique_search_parse",
                "course_plan_generate",
            ]
            if llm_service.is_enabled()
            else []
        ),
    )


@router.get(
    "/brief/{teacher_id}",
    response_model=BriefResponse,
    dependencies=[Depends(ai_rate_limit)],
    summary="What should we actually do together?",
    description=(
        "Turns a match into a plan: a short proposal grounded in both profiles, "
        "the component scores behind the match, and the resources that educator "
        "has shared. Nothing outside those facts is used."
    ),
)
async def collaboration_brief(teacher_id: uuid.UUID, current_user: CurrentUser, db: DB) -> BriefResponse:
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    if teacher_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That is your own profile."
        )

    key = (current_user.id, teacher_id)
    cached = _BRIEF_CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return BriefResponse(brief=cached[1], teacher_id=teacher_id, cached=True)

    viewer = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if viewer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create your profile first - the brief is written from it.",
        )
    row = (
        await db.execute(
            select(TeacherProfile, User)
            .join(User, User.id == TeacherProfile.user_id)
            .where(TeacherProfile.user_id == teacher_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Educator not found")
    match_profile, match_user = row

    breakdown = score_profiles(viewer, match_profile)
    resources = list(
        (
            await db.scalars(
                select(Resource).where(Resource.owner_id == teacher_id).limit(5)
            )
        ).all()
    )

    try:
        brief = await llm_service.collaboration_brief(
            viewer,
            current_user.first_name,
            match_profile,
            f"{match_user.first_name} {match_user.last_name}",
            components=breakdown.components,
            shared_terms=breakdown.shared_terms,
            distance_km=breakdown.distance_km,
            resources=resources,
        )
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    _BRIEF_CACHE[key] = (time.time(), brief)
    return BriefResponse(brief=brief, teacher_id=teacher_id)


@router.post(
    "/profile-from-document",
    response_model=ProfileDraft,
    dependencies=[Depends(ai_rate_limit)],
    summary="Fill a profile from a syllabus",
    description=(
        "Upload a syllabus, lesson plan or course outline (PDF, TXT or Markdown) "
        "and get back a suggested profile to review. Nothing is saved - the "
        "response is a draft for the teacher to edit and submit."
    ),
)
async def profile_from_document(
    current_user: CurrentUser,
    file: Annotated[UploadFile | None, File(description="PDF, TXT or Markdown")] = None,
    text: Annotated[str | None, Form(description="Paste the text instead of a file")] = None,
) -> ProfileDraft:
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    if file is None and not (text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Attach a document or paste some text."
        )

    pdf_bytes: bytes | None = None
    document_text: str | None = text
    source_name: str | None = None

    if file is not None:
        source_name = os.path.basename(file.filename or "document")
        extension = os.path.splitext(source_name)[1].lower()
        if extension not in TEXT_EXTENSIONS | PDF_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Upload a PDF, TXT or Markdown file - '{extension or 'unknown'}' is not supported.",
            )
        data = await file.read(MAX_DOCUMENT_BYTES + 1)
        if len(data) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Documents are limited to {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB.",
            )
        if extension in PDF_EXTENSIONS:
            pdf_bytes = data
        else:
            document_text = data.decode("utf-8", errors="replace")

    try:
        extracted = await llm_service.extract_profile_from_document(
            document_text, pdf=pdf_bytes
        )
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return ProfileDraft(**extracted.model_dump(), source_name=source_name)
