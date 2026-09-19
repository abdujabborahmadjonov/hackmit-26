"""Account-level endpoints (the profile lives under /profiles)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.common import Message
from app.schemas.user import UserPrivate, UserPublic, UserUpdate
from app.utils.auth import CurrentUser

router = APIRouter(prefix="/users", tags=["users"])

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/me", response_model=UserPrivate, summary="Your own account")
async def get_me(current_user: CurrentUser) -> UserPrivate:
    return UserPrivate.model_validate(current_user)


@router.put("/me", response_model=UserPrivate, summary="Update your account")
async def update_me(payload: UserUpdate, current_user: CurrentUser, db: DB) -> UserPrivate:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return UserPrivate.model_validate(current_user)


@router.delete(
    "/me",
    response_model=Message,
    summary="Deactivate your account",
    description="Soft-deletes the account: it stops appearing in search and recommendations.",
)
async def deactivate_me(current_user: CurrentUser, db: DB) -> Message:
    current_user.is_active = False
    await db.commit()
    return Message(detail="Account deactivated")


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Public information about an educator",
)
async def get_user(user_id: uuid.UUID, db: DB, _: CurrentUser) -> UserPublic:
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublic.model_validate(user)
