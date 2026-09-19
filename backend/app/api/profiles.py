"""Teacher profiles - the input to every match EduMatch makes."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import TeacherProfile
from app.models.user import User
from app.schemas.common import Message
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate
from app.services import elasticsearch_service as es
from app.services.embedding_service import EmbeddingError
from app.services.profile_service import refresh_profile_embedding, sync_profile_to_index
from app.utils.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["profiles"])

DB = Annotated[AsyncSession, Depends(get_db)]

# Fields that change the meaning of a teacher's pedagogy, and therefore require
# the embedding to be regenerated.
EMBEDDING_FIELDS = {
    "bio",
    "teaching_style",
    "teaching_methods",
    "fields_of_expertise",
    "subjects",
    "education_levels",
}


async def _regenerate_embedding(profile: TeacherProfile) -> None:
    try:
        await refresh_profile_embedding(profile)
    except EmbeddingError as exc:
        logger.error("Embedding generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not generate the teaching-style embedding: {exc}",
        ) from exc


@router.post(
    "",
    response_model=ProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create your teacher profile",
    description=(
        "Creates the authenticated user's profile and immediately generates the "
        "teaching-style embedding used by search and recommendations. "
        "Submit an approximate (city-level) location only."
    ),
)
async def create_profile(
    payload: ProfileCreate, current_user: CurrentUser, db: DB
) -> ProfileRead:
    existing = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists - use PUT /profiles/me to update it",
        )

    profile = TeacherProfile(user_id=current_user.id, **payload.model_dump())
    await _regenerate_embedding(profile)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    await sync_profile_to_index(db, profile)
    return ProfileRead.from_model(profile, user=current_user)


@router.get("/me", response_model=ProfileRead, summary="Your own profile")
async def get_my_profile(current_user: CurrentUser, db: DB) -> ProfileRead:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You have not created a profile yet",
        )
    return ProfileRead.from_model(profile, user=current_user)


@router.put(
    "/me",
    response_model=ProfileRead,
    summary="Update your profile",
    description=(
        "Partial update. The teaching-style embedding is regenerated only when a "
        "field that feeds it changes, which keeps writes cheap."
    ),
)
async def update_my_profile(
    payload: ProfileUpdate, current_user: CurrentUser, db: DB
) -> ProfileRead:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create a profile first with POST /profiles",
        )

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    if EMBEDDING_FIELDS & updates.keys():
        await _regenerate_embedding(profile)

    await db.commit()
    await db.refresh(profile)
    await sync_profile_to_index(db, profile)
    return ProfileRead.from_model(profile, user=current_user)


@router.delete("/me", response_model=Message, summary="Delete your profile")
async def delete_my_profile(current_user: CurrentUser, db: DB) -> Message:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile to delete")
    await db.delete(profile)
    await db.commit()
    await es.delete_teacher(current_user.id)
    return Message(detail="Profile deleted")


@router.get(
    "/{user_id}",
    response_model=ProfileRead,
    summary="View another educator's profile",
)
async def get_profile(user_id: uuid.UUID, db: DB, _: CurrentUser) -> ProfileRead:
    row = (
        await db.execute(
            select(TeacherProfile, User)
            .join(User, User.id == TeacherProfile.user_id)
            .where(TeacherProfile.user_id == user_id, User.is_active.is_(True))
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    profile, user = row
    return ProfileRead.from_model(profile, user=user)
