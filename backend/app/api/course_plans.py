"""Course plan generation and CRUD for educators."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import Message as MessageEnvelope
from app.schemas.common import Page
from app.schemas.course_plan import (
    CoursePlanGenerateRequest,
    CoursePlanGenerationFailure,
    CoursePlanRead,
    CoursePlanRegenerateRequest,
    CoursePlanStructureUpdate,
    CoursePlanSummary,
    CoursePlanUpdate,
)
from app.services import course_plan_service, llm_service
from app.services.course_plan_service import CoursePlanGenerationError
from app.services.llm_service import LLMUnavailable
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/course-plans", tags=["course-plans"])
DB = Annotated[AsyncSession, Depends(get_db)]
ai_rate_limit = RateLimiter("ai", 20)


async def _owned(db: AsyncSession, plan_id: uuid.UUID, teacher_id: uuid.UUID):
    plan = await course_plan_service.get_owned_plan(db, plan_id, teacher_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course plan not found"
        )
    return plan


async def _to_read(db: AsyncSession, plan) -> CoursePlanRead:
    similar = await course_plan_service.load_similar_classes(
        db, list(plan.similar_class_ids or [])
    )
    return course_plan_service.serialize_plan(plan, similar_classes=similar)


def _generation_http(exc: CoursePlanGenerationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=CoursePlanGenerationFailure(
            reason=exc.reason,
            resource_candidates=exc.resource_candidates,
            technique_candidates=exc.technique_candidates,
            similar_classes=exc.similar_classes,
        ).model_dump(),
    )


@router.get("", response_model=Page[CoursePlanSummary], summary="List my course plans")
async def list_course_plans(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CoursePlanSummary]:
    rows = await course_plan_service.list_plans(
        db, current_user.id, limit=limit, offset=offset
    )
    return Page(
        items=[course_plan_service.serialize_summary(r) for r in rows],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/generate",
    response_model=CoursePlanRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(ai_rate_limit)],
    summary="Generate a course plan + planned class from a brief",
)
async def generate_course_plan(
    payload: CoursePlanGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> CoursePlanRead:
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    try:
        plan = await course_plan_service.generate_plan(db, current_user.id, payload)
    except CoursePlanGenerationError as exc:
        raise _generation_http(exc) from exc
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return await _to_read(db, plan)


@router.get("/{plan_id}", response_model=CoursePlanRead)
async def get_course_plan(
    plan_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> CoursePlanRead:
    plan = await _owned(db, plan_id, current_user.id)
    return await _to_read(db, plan)


@router.put("/{plan_id}", response_model=CoursePlanRead, summary="Update plan metadata")
async def update_course_plan(
    plan_id: uuid.UUID,
    payload: CoursePlanUpdate,
    current_user: CurrentUser,
    db: DB,
) -> CoursePlanRead:
    plan = await _owned(db, plan_id, current_user.id)
    plan = await course_plan_service.update_metadata(db, plan, payload)
    return await _to_read(db, plan)


@router.put(
    "/{plan_id}/structure",
    response_model=CoursePlanRead,
    summary="Replace units/sessions/items (manual edit)",
)
async def update_course_plan_structure(
    plan_id: uuid.UUID,
    payload: CoursePlanStructureUpdate,
    current_user: CurrentUser,
    db: DB,
) -> CoursePlanRead:
    plan = await _owned(db, plan_id, current_user.id)
    try:
        plan = await course_plan_service.replace_structure(db, plan, payload)
    except CoursePlanGenerationError as exc:
        raise _generation_http(exc) from exc
    return await _to_read(db, plan)


@router.post(
    "/{plan_id}/regenerate",
    response_model=CoursePlanRead,
    dependencies=[Depends(ai_rate_limit)],
    summary="Regenerate the entire course plan",
)
async def regenerate_course_plan(
    plan_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
    payload: CoursePlanRegenerateRequest | None = None,
) -> CoursePlanRead:
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    plan = await _owned(db, plan_id, current_user.id)
    try:
        plan = await course_plan_service.regenerate_plan(db, plan, payload)
    except CoursePlanGenerationError as exc:
        raise _generation_http(exc) from exc
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return await _to_read(db, plan)


@router.post(
    "/{plan_id}/units/{unit_id}/regenerate",
    response_model=CoursePlanRead,
    dependencies=[Depends(ai_rate_limit)],
    summary="Regenerate a single unit",
)
async def regenerate_course_plan_unit(
    plan_id: uuid.UUID,
    unit_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> CoursePlanRead:
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Generative features are not configured on this deployment.",
        )
    plan = await _owned(db, plan_id, current_user.id)
    try:
        plan = await course_plan_service.regenerate_unit(db, plan, unit_id)
    except CoursePlanGenerationError as exc:
        raise _generation_http(exc) from exc
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return await _to_read(db, plan)


@router.delete("/{plan_id}", response_model=MessageEnvelope)
async def delete_course_plan(
    plan_id: uuid.UUID, current_user: CurrentUser, db: DB
) -> MessageEnvelope:
    plan = await _owned(db, plan_id, current_user.id)
    await course_plan_service.delete_plan(db, plan)
    return MessageEnvelope(detail="Course plan deleted")
