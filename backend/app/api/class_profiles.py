"""CRUD for per-class teaching profiles."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.class_profile import ClassProfile
from app.schemas.class_profile import (
    ClassProfileCreate,
    ClassProfileDraft,
    ClassProfilePromote,
    ClassProfileRead,
    ClassProfileUpdate,
)
from app.schemas.common import Message as MessageEnvelope
from app.schemas.common import Page
from app.services import llm_service
from app.services.llm_service import LLMUnavailable
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/class-profiles", tags=["class-profiles"])
DB = Annotated[AsyncSession, Depends(get_db)]
ai_rate_limit = RateLimiter("ai", 20)

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
PDF_EXTENSIONS = {".pdf"}
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


async def _owned(db: AsyncSession, profile_id: uuid.UUID, teacher_id: uuid.UUID) -> ClassProfile:
    row = await db.scalar(
        select(ClassProfile).where(
            ClassProfile.id == profile_id,
            ClassProfile.teacher_id == teacher_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class profile not found")
    return row


@router.get("", response_model=Page[ClassProfileRead], summary="List my class profiles")
async def list_class_profiles(
    current_user: CurrentUser,
    db: DB,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ClassProfileRead]:
    query = select(ClassProfile).where(ClassProfile.teacher_id == current_user.id)
    if status_filter:
        query = query.where(ClassProfile.status == status_filter)
    rows = (
        await db.scalars(
            query.order_by(ClassProfile.updated_at.desc()).limit(limit).offset(offset)
        )
    ).all()
    return Page(items=[ClassProfileRead.model_validate(r) for r in rows], total=len(rows), limit=limit, offset=offset)


@router.post("", response_model=ClassProfileRead, status_code=status.HTTP_201_CREATED)
async def create_class_profile(
    payload: ClassProfileCreate, current_user: CurrentUser, db: DB
) -> ClassProfileRead:
    row = ClassProfile(teacher_id=current_user.id, **payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ClassProfileRead.model_validate(row)


@router.get("/{profile_id}", response_model=ClassProfileRead)
async def get_class_profile(
    profile_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> ClassProfileRead:
    row = await _owned(db, profile_id, current_user.id)
    return ClassProfileRead.model_validate(row)


@router.put("/{profile_id}", response_model=ClassProfileRead)
async def update_class_profile(
    profile_id: uuid.UUID,
    payload: ClassProfileUpdate,
    current_user: CurrentUser,
    db: DB,
) -> ClassProfileRead:
    row = await _owned(db, profile_id, current_user.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return ClassProfileRead.model_validate(row)


@router.post("/{profile_id}/promote", response_model=ClassProfileRead)
async def promote_class_profile(
    profile_id: uuid.UUID,
    payload: ClassProfilePromote,
    current_user: CurrentUser,
    db: DB,
) -> ClassProfileRead:
    row = await _owned(db, profile_id, current_user.id)
    if row.status != "planned":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only planned class profiles can be promoted to active",
        )
    row.status = "active"
    row.class_size = payload.class_size
    row.class_size_min = None
    row.class_size_max = None
    if payload.format:
        row.format = payload.format
    if payload.notes is not None:
        row.notes = payload.notes
    await db.commit()
    await db.refresh(row)
    return ClassProfileRead.model_validate(row)


@router.delete("/{profile_id}", response_model=MessageEnvelope)
async def delete_class_profile(
    profile_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    row = await _owned(db, profile_id, current_user.id)
    await db.delete(row)
    await db.commit()
    return MessageEnvelope(detail="Class profile deleted")


@router.post(
    "/from-document",
    response_model=ClassProfileDraft,
    dependencies=[Depends(ai_rate_limit)],
    summary="Prefill a class profile from a syllabus",
)
async def class_from_document(
    current_user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
) -> ClassProfileDraft:
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
        extracted = await llm_service.extract_class_from_document(
            document_text, pdf=pdf_bytes
        )
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    data = extracted.as_api_fields()
    fmt = (data.get("format") or "").strip().lower() if data.get("format") else ""
    if fmt not in ("lecture", "lab", "online", "hybrid"):
        data["format"] = None
    else:
        data["format"] = fmt
    return ClassProfileDraft(**data)
