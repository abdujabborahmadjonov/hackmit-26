"""Classroom verification tokens educators share with students."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import Message, Page
from app.schemas.rating import StudentTokenCreate, StudentTokenCreated, StudentTokenRead
from app.services import verification_service
from app.utils.auth import CurrentUser

router = APIRouter(tags=["student-tokens"])

DB = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/teachers/me/student-tokens",
    response_model=StudentTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a classroom verification token",
    description=(
        "Generates a short code students enter to submit a verified rating. "
        "Set `duration_minutes` to control how long the code stays valid. "
        "The plaintext code is returned only in this response."
    ),
)
async def create_my_student_token(
    payload: StudentTokenCreate, current_user: CurrentUser, db: DB
) -> StudentTokenCreated:
    token, plaintext = await verification_service.create_student_token(
        db,
        teacher_id=current_user.id,
        duration_minutes=payload.duration_minutes,
        label=payload.label,
        max_uses=payload.max_uses,
    )
    await db.commit()
    await db.refresh(token)
    fields = verification_service.token_to_read_fields(token)
    return StudentTokenCreated(**fields, token=plaintext)


@router.get(
    "/teachers/me/student-tokens",
    response_model=Page[StudentTokenRead],
    summary="List your classroom verification tokens",
)
async def list_my_student_tokens(current_user: CurrentUser, db: DB) -> Page[StudentTokenRead]:
    rows = await verification_service.list_student_tokens(db, current_user.id)
    items = [
        StudentTokenRead(**verification_service.token_to_read_fields(row)) for row in rows
    ]
    return Page[StudentTokenRead](items=items, total=len(items), limit=len(items), offset=0)


@router.delete(
    "/teachers/me/student-tokens/{token_id}",
    response_model=Message,
    summary="Revoke a classroom verification token",
)
async def revoke_my_student_token(
    token_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> Message:
    await verification_service.revoke_student_token(
        db, teacher_id=current_user.id, token_id=token_id
    )
    await db.commit()
    return Message(detail="Token revoked")
