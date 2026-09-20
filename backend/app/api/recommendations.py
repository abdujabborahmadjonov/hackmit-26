"""Recommendations - "which educators should I collaborate with?"."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import normalise_recommendation_weights
from app.database import get_db
from app.models.profile import TeacherProfile
from app.models.recommendation import RecommendationEvent, RecommendationFeedback
from app.schemas.common import Message
from app.schemas.profile import profile_summary
from app.schemas.recommendation import (
    MatchReason,
    Recommendation,
    RecommendationFeedbackRequest,
    RecommendationResponse,
    RecommendationWeightsRead,
    RecommendationWeightsUpdate,
)
from app.services import bandit_service
from app.services.recommendation_service import (
    ProfileRequiredError,
    RecommendationService,
    build_reasons,
    score_profiles,
)
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
        "Hybrid ranking over a pgvector candidate pool with social graph and "
        "Bayesian quality signals, optional MMR diversity, and Thompson-sampling "
        "weight arms (or your saved profile weights). Every result carries "
        "plain-language reasons plus a structured explanation array."
    ),
)
async def get_recommendations(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=50, description="How many matches to return")] = 10,
    exclude_connected: Annotated[
        bool,
        Query(
            description="Hide people you are already connected to or have pending requests with"
        ),
    ] = False,
    candidate_pool: Annotated[
        int | None, Query(ge=10, le=2000, description="Override the ANN candidate pool size")
    ] = None,
    mmr: Annotated[
        bool | None, Query(description="Override REC_MMR_ENABLED for this request")
    ] = None,
) -> RecommendationResponse:
    service = RecommendationService(db)
    try:
        result = await service.recommend(
            current_user.id,
            limit=limit,
            exclude_connected=exclude_connected,
            pool_size=candidate_pool,
            mmr=mmr,
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
        bandit_arm_id=result.bandit_arm_id,
        weight_source=result.weight_source,
    )


@router.get(
    "/weights",
    response_model=RecommendationWeightsRead,
    summary="Your recommendation weight preferences",
)
async def get_weights(current_user: CurrentUser, db: DB) -> RecommendationWeightsRead:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create your teacher profile first.",
        )
    selected = await bandit_service.resolve_weights(
        db, profile_weights=profile.recommendation_weights
    )
    return RecommendationWeightsRead(
        weights={k: round(v, 4) for k, v in selected.weights.items()},
        saved=profile.recommendation_weights is not None,
        source=selected.source,
        bandit_arm_id=selected.arm_id,
    )


@router.put(
    "/weights",
    response_model=RecommendationWeightsRead,
    summary="Save personal recommendation weights",
    description="Persists on your teacher profile and overrides the bandit while set.",
)
async def put_weights(
    payload: RecommendationWeightsUpdate,
    current_user: CurrentUser,
    db: DB,
) -> RecommendationWeightsRead:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create your teacher profile first.",
        )
    try:
        weights = normalise_recommendation_weights(payload.weights)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    profile.recommendation_weights = weights
    await db.commit()
    return RecommendationWeightsRead(
        weights={k: round(v, 4) for k, v in weights.items()},
        saved=True,
        source="profile",
        bandit_arm_id=None,
    )


@router.delete(
    "/weights",
    response_model=RecommendationWeightsRead,
    summary="Clear personal weights (return to bandit / defaults)",
)
async def delete_weights(current_user: CurrentUser, db: DB) -> RecommendationWeightsRead:
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Create your teacher profile first.",
        )
    profile.recommendation_weights = None
    await db.commit()
    selected = await bandit_service.resolve_weights(db, profile_weights=None)
    return RecommendationWeightsRead(
        weights={k: round(v, 4) for k, v in selected.weights.items()},
        saved=False,
        source=selected.source,
        bandit_arm_id=selected.arm_id,
    )


@router.get(
    "/{user_id}/explain",
    response_model=Recommendation,
    summary="Why this match?",
    description="Full score breakdown between you and one specific educator.",
)
async def explain_match(user_id: uuid.UUID, current_user: CurrentUser, db: DB) -> Recommendation:
    from app.models.user import User

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
    social_map = await service._social_scores(viewer.user_id, [candidate.user_id])
    social_score, shared_n = social_map.get(candidate.user_id, (0.0, 0))

    # Prefer the weights that actually served this pair (stable "why this match?").
    event = await db.scalar(
        select(RecommendationEvent).where(
            RecommendationEvent.user_id == current_user.id,
            RecommendationEvent.recommended_user_id == user_id,
        )
    )
    weights = None
    if event is not None and event.bandit_arm_id:
        from app.models.recommendation import BanditArm

        arm = await db.get(BanditArm, event.bandit_arm_id)
        if arm is not None:
            weights = normalise_recommendation_weights(arm.weights)
    if weights is None:
        selected = await bandit_service.resolve_weights(
            db, profile_weights=viewer.recommendation_weights, bandit_enabled=False
        )
        weights = selected.weights

    breakdown = score_profiles(
        viewer,
        candidate,
        weights,
        social_score=social_score,
        shared_neighbors=shared_n,
    )
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
    description="Updates the Thompson-sampling arm that served this match.",
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

    event = await db.scalar(
        select(RecommendationEvent).where(
            RecommendationEvent.user_id == current_user.id,
            RecommendationEvent.recommended_user_id == user_id,
        )
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recommendation found for that educator",
        )

    event.feedback = feedback
    await bandit_service.record_feedback(db, arm_id=event.bandit_arm_id, feedback=feedback)
    await db.commit()
    return Message(detail="Feedback recorded")
