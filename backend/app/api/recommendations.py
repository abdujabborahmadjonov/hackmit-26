"""Recommendations - "which educators should I collaborate with?"."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.recommendation import RecommendationEvent, RecommendationFeedback
from app.schemas.common import Message
from app.schemas.profile import profile_summary
from app.schemas.recommendation import (
    MatchReason,
    Recommendation,
    RecommendationFeedbackRequest,
    RecommendationResponse,
)
from app.services.recommendation_service import ProfileRequiredError, RecommendationService
from app.utils.auth import CurrentUser
from app.utils.rate_limit import default_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(default_rate_limit)],
)

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "",
    response_model=RecommendationResponse,
    summary="Top educator matches for you",
    description=(
        "Hybrid ranking over a pgvector candidate pool:\n\n"
        "* 30% semantic teaching-style similarity\n"
        "* 20% subject / expertise overlap\n"
        "* 15% education-level compatibility\n"
        "* 15% teaching-level compatibility\n"
        "* 10% geographic proximity\n"
        "* 10% class-size similarity\n\n"
        "Every result carries plain-language reasons plus a structured "
        "`explanation` array for a \"Why this match?\" panel. Weights are "
        "configurable through REC_WEIGHT_* environment variables."
    ),
)
async def get_recommendations(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=50, description="How many matches to return")] = 10,
    exclude_connected: Annotated[
        bool, Query(description="Hide people you are already connected to or have pending requests with")
    ] = False,
    candidate_pool: Annotated[
        int | None, Query(ge=10, le=2000, description="Override the ANN candidate pool size")
    ] = None,
) -> RecommendationResponse:
    service = RecommendationService(db)
    try:
        result = await service.recommend(
            current_user.id,
            limit=limit,
            exclude_connected=exclude_connected,
            pool_size=candidate_pool,
        )
    except ProfileRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    items = [
        Recommendation(
            teacher=profile_summary(item.profile, item.user, item.breakdown.distance_km),
            match_score=round(item.breakdown.total, 4),
            components={k: round(v, 4) for k, v in item.breakdown.components.items()},
            reasons=item.reasons,
            explanation=[MatchReason(**entry) for entry in item.explanation],
            distance_km=round(item.breakdown.distance_km, 1)
            if item.breakdown.distance_km is not None
            else None,
        )
        for item in result.items
    ]
    return RecommendationResponse(
        items=items,
        generated_for=current_user.id,
        candidate_pool_size=result.candidate_pool_size,
        took_ms=result.took_ms,
        weights={k: round(v, 4) for k, v in result.weights.items()},
    )


@router.get(
    "/{user_id}/explain",
    response_model=Recommendation,
    summary="Why this match?",
    description="Full score breakdown between you and one specific educator.",
)
async def explain_match(user_id: uuid.UUID, current_user: CurrentUser, db: DB) -> Recommendation:
    from app.models.profile import TeacherProfile
    from app.models.user import User
    from app.services.recommendation_service import build_reasons, score_profiles

    service = RecommendationService(db)
    viewer = await service._load_profile(current_user.id)
    if viewer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create your teacher profile first - matching is based on it.",
        )
    row = (
        await db.execute(
            select(TeacherProfile, User)
            .join(User, User.id == TeacherProfile.user_id)
            .where(TeacherProfile.user_id == user_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    candidate, user = row
    breakdown = score_profiles(viewer, candidate)
    reasons, explanation = build_reasons(breakdown, viewer, candidate, max_reasons=6)
    return Recommendation(
        teacher=profile_summary(candidate, user, breakdown.distance_km),
        match_score=round(breakdown.total, 4),
        components={k: round(v, 4) for k, v in breakdown.components.items()},
        reasons=reasons,
        explanation=[MatchReason(**entry) for entry in explanation],
        distance_km=round(breakdown.distance_km, 1) if breakdown.distance_km is not None else None,
    )


@router.post(
    "/{user_id}/feedback",
    response_model=Message,
    summary="Record feedback on a recommendation",
    description="Feeds future weight tuning: none | saved | dismissed | connected.",
)
async def submit_feedback(
    user_id: uuid.UUID,
    payload: RecommendationFeedbackRequest,
    current_user: CurrentUser,
    db: DB,
) -> Message:
    try:
        feedback = RecommendationFeedback(payload.feedback)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"feedback must be one of {[f.value for f in RecommendationFeedback]}",
        ) from None

    result = await db.execute(
        update(RecommendationEvent)
        .where(
            RecommendationEvent.user_id == current_user.id,
            RecommendationEvent.recommended_user_id == user_id,
        )
        .values(feedback=feedback)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recommendation found for that educator",
        )
    return Message(detail="Feedback recorded")
