"""Ratings and written reviews for educators."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.connection import Connection, ConnectionStatus
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.rating import RatingCreate, RatingRead, RatingSummary, RatingUpdate
from app.services.profile_service import recalculate_teacher_rating, sync_profile_to_index
from app.utils.auth import CurrentUser, OptionalUser

router = APIRouter(tags=["ratings"])

DB = Annotated[AsyncSession, Depends(get_db)]


async def _refresh_rollup(db: AsyncSession, teacher_id: uuid.UUID) -> None:
    await recalculate_teacher_rating(db, teacher_id)
    await db.commit()
    profile = await db.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher_id))
    if profile is not None:
        await sync_profile_to_index(db, profile)


@router.post(
    "/teachers/{teacher_id}/ratings",
    response_model=RatingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Rate an educator",
    description=(
        "One rating per reviewer per teacher. Posting again returns 409 - use "
        "PUT to change your existing rating. The teacher's `average_rating` and "
        "`rating_count` are recalculated automatically."
    ),
)
async def create_rating(
    teacher_id: uuid.UUID, payload: RatingCreate, current_user: CurrentUser, db: DB
) -> RatingRead:
    if teacher_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot rate yourself"
        )
    teacher = await db.scalar(select(User).where(User.id == teacher_id, User.is_active.is_(True)))
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Educator not found")

    existing = await db.scalar(
        select(Rating).where(
            Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already rated this educator - use PUT to update your rating",
        )

    # A connection between the two accounts is our (weak) proxy for a verified
    # working relationship. It is advisory metadata, not a trust claim.
    connected = await db.scalar(
        select(Connection.id).where(
            Connection.status == ConnectionStatus.ACCEPTED,
            (
                (Connection.requester_id == current_user.id)
                & (Connection.receiver_id == teacher_id)
            )
            | (
                (Connection.receiver_id == current_user.id)
                & (Connection.requester_id == teacher_id)
            ),
        )
    )

    rating = Rating(
        reviewer_id=current_user.id,
        teacher_id=teacher_id,
        rating=payload.rating,
        comment=payload.comment,
        is_verified_student=bool(connected),
    )
    db.add(rating)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You already rated this educator"
        ) from None
    await db.refresh(rating)
    await _refresh_rollup(db, teacher_id)
    return RatingRead.model_validate(rating)


@router.put(
    "/teachers/{teacher_id}/ratings",
    response_model=RatingRead,
    summary="Update your rating for an educator",
)
async def update_rating(
    teacher_id: uuid.UUID, payload: RatingUpdate, current_user: CurrentUser, db: DB
) -> RatingRead:
    rating = await db.scalar(
        select(Rating).where(
            Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id
        )
    )
    if rating is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="You have not rated this educator yet"
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rating, field, value)
    await db.commit()
    await db.refresh(rating)
    await _refresh_rollup(db, teacher_id)
    return RatingRead.model_validate(rating)


@router.delete(
    "/teachers/{teacher_id}/ratings",
    response_model=Message,
    summary="Delete your rating",
)
async def delete_rating(teacher_id: uuid.UUID, current_user: CurrentUser, db: DB) -> Message:
    rating = await db.scalar(
        select(Rating).where(
            Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id
        )
    )
    if rating is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rating not found")
    await db.delete(rating)
    await db.commit()
    await _refresh_rollup(db, teacher_id)
    return Message(detail="Rating deleted")


@router.get(
    "/teachers/{teacher_id}/ratings",
    response_model=Page[RatingRead],
    summary="Reviews for an educator",
)
async def list_ratings(
    teacher_id: uuid.UUID,
    db: DB,
    _: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RatingRead]:
    total = await db.scalar(
        select(func.count()).select_from(Rating).where(Rating.teacher_id == teacher_id)
    ) or 0
    rows = (
        await db.scalars(
            select(Rating)
            .where(Rating.teacher_id == teacher_id)
            .order_by(Rating.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).unique().all()
    return Page[RatingRead](
        items=[RatingRead.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/teachers/{teacher_id}/ratings/summary",
    response_model=RatingSummary,
    summary="Rating distribution for an educator",
)
async def rating_summary(teacher_id: uuid.UUID, db: DB, _: OptionalUser) -> RatingSummary:
    rows = (
        await db.execute(
            select(Rating.rating, func.count(Rating.id))
            .where(Rating.teacher_id == teacher_id)
            .group_by(Rating.rating)
        )
    ).all()
    distribution = {int(value): int(count) for value, count in rows}
    total = sum(distribution.values())
    average = (
        sum(value * count for value, count in distribution.items()) / total if total else 0.0
    )
    return RatingSummary(
        teacher_id=teacher_id,
        average_rating=round(average, 2),
        rating_count=total,
        distribution=distribution,
    )
