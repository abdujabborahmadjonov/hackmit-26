"""Ratings and written reviews for educators."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.rating import (
    AspectAverages,
    RatingCreate,
    RatingRead,
    RatingSummary,
    RatingUpdate,
)
from app.services import verification_service
from app.services.profile_service import recalculate_teacher_rating, sync_profile_to_index
from app.utils.auth import CurrentUser, OptionalUser

router = APIRouter(tags=["ratings"])

DB = Annotated[AsyncSession, Depends(get_db)]

_ASPECT_FIELDS = (
    "knowledge_of_material",
    "presentation",
    "friendliness",
    "other",
)


def _overall_from_payload(payload: RatingCreate | RatingUpdate) -> int | None:
    aspects = [getattr(payload, field) for field in _ASPECT_FIELDS if getattr(payload, field, None) is not None]
    if len(aspects) == 4:
        # Half-up so a 4.5 average becomes 5 stars (not banker's rounding).
        return max(1, min(5, int(sum(aspects) / 4 + 0.5)))
    return getattr(payload, "rating", None)


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
        "PUT to change your existing rating. Include a `verification_token` plus "
        "all four aspect scores for a verified student rating. The teacher's "
        "`average_rating` and `rating_count` are recalculated automatically."
    ),
)
async def create_rating(teacher_id: uuid.UUID, payload: RatingCreate, current_user: CurrentUser, db: DB) -> RatingRead:
    if teacher_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot rate yourself")
    teacher = await db.scalar(select(User).where(User.id == teacher_id, User.is_active.is_(True)))
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Educator not found")

    existing = await db.scalar(
        select(Rating).where(Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already rated this educator - use PUT to update your rating",
        )

    verification_token_id: uuid.UUID | None = None
    is_verified_student = False
    if payload.verification_token:
        redeemed = await verification_service.redeem_student_token(
            db, teacher_id=teacher_id, plaintext=payload.verification_token
        )
        verification_token_id = redeemed.id
        is_verified_student = True

    overall = _overall_from_payload(payload)
    if overall is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide an overall rating or all four aspect scores",
        )

    rating = Rating(
        reviewer_id=current_user.id,
        teacher_id=teacher_id,
        rating=overall,
        comment=payload.comment,
        knowledge_of_material=payload.knowledge_of_material,
        presentation=payload.presentation,
        friendliness=payload.friendliness,
        other=payload.other,
        is_verified_student=is_verified_student,
        verification_token_id=verification_token_id,
    )
    db.add(rating)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already rated this educator") from None
    await db.refresh(rating)
    await _refresh_rollup(db, teacher_id)
    return RatingRead.model_validate(rating)


@router.put(
    "/teachers/{teacher_id}/ratings",
    response_model=RatingRead,
    summary="Update your rating for an educator",
)
async def update_rating(teacher_id: uuid.UUID, payload: RatingUpdate, current_user: CurrentUser, db: DB) -> RatingRead:
    rating = await db.scalar(
        select(Rating).where(Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id)
    )
    if rating is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You have not rated this educator yet")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(rating, field, value)
    overall = _overall_from_payload(payload)
    if overall is not None and "rating" not in data:
        rating.rating = overall
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
        select(Rating).where(Rating.reviewer_id == current_user.id, Rating.teacher_id == teacher_id)
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
    total = await db.scalar(select(func.count()).select_from(Rating).where(Rating.teacher_id == teacher_id)) or 0
    rows = (
        (
            await db.scalars(
                select(Rating)
                .where(Rating.teacher_id == teacher_id)
                .order_by(Rating.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .unique()
        .all()
    )
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
            select(Rating.rating, func.count(Rating.id)).where(Rating.teacher_id == teacher_id).group_by(Rating.rating)
        )
    ).all()
    distribution = {int(value): int(count) for value, count in rows}
    total = sum(distribution.values())
    average = sum(value * count for value, count in distribution.items()) / total if total else 0.0

    verified_count = (
        await db.scalar(
            select(func.count())
            .select_from(Rating)
            .where(Rating.teacher_id == teacher_id, Rating.is_verified_student.is_(True))
        )
        or 0
    )

    aspect_avgs = (
        await db.execute(
            select(
                func.avg(Rating.knowledge_of_material),
                func.avg(Rating.presentation),
                func.avg(Rating.friendliness),
                func.avg(Rating.other),
            ).where(
                Rating.teacher_id == teacher_id,
                Rating.is_verified_student.is_(True),
                Rating.knowledge_of_material.is_not(None),
            )
        )
    ).one()

    def _round(value: float | None) -> float | None:
        return round(float(value), 2) if value is not None else None

    return RatingSummary(
        teacher_id=teacher_id,
        average_rating=round(average, 2),
        rating_count=total,
        verified_student_count=int(verified_count),
        distribution=distribution,
        aspect_averages=AspectAverages(
            knowledge_of_material=_round(aspect_avgs[0]),
            presentation=_round(aspect_avgs[1]),
            friendliness=_round(aspect_avgs[2]),
            other=_round(aspect_avgs[3]),
        ),
    )
