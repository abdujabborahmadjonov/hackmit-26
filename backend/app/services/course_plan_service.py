"""Retrieve-then-generate course plans grounded in library + peer classes."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.class_profile import ClassProfile
from app.models.course_plan import (
    CoursePlan,
    CoursePlanItem,
    CoursePlanSession,
    CoursePlanUnit,
)
from app.models.resource import Resource
from app.models.technique import Technique
from app.schemas.course_plan import (
    CoursePlanGenerateRequest,
    CoursePlanItemRead,
    CoursePlanRead,
    CoursePlanRegenerateRequest,
    CoursePlanSessionRead,
    CoursePlanStructureUpdate,
    CoursePlanSummary,
    CoursePlanUnitInput,
    CoursePlanUnitRead,
    CoursePlanUpdate,
)
from app.services import llm_service
from app.services.llm_service import GeneratedCoursePlan, LLMUnavailable
from app.taxonomy import fields_compatible, humanize

logger = logging.getLogger(__name__)

MIN_RESOURCES_FOR_CONFIDENCE = 3
RESOURCE_POOL = 40
TECHNIQUE_POOL = 30
SIMILAR_CLASS_POOL = 8


class CoursePlanGenerationError(Exception):
    """Not enough grounded material, or the model declined to invent."""

    def __init__(
        self,
        reason: str,
        *,
        resource_candidates: int = 0,
        technique_candidates: int = 0,
        similar_classes: int = 0,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.resource_candidates = resource_candidates
        self.technique_candidates = technique_candidates
        self.similar_classes = similar_classes


@dataclass
class RetrievalBundle:
    resources: list[Resource] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    similar_classes: list[ClassProfile] = field(default_factory=list)

    @property
    def resource_ids(self) -> set[uuid.UUID]:
        return {r.id for r in self.resources}

    @property
    def technique_ids(self) -> set[uuid.UUID]:
        return {t.id for t in self.techniques}


async def retrieve_candidates(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    subject: str,
    level: str,
    exclude_class_id: uuid.UUID | None = None,
) -> RetrievalBundle:
    """Pull library resources/techniques and similar peer class profiles."""
    resources = list(
        (
            await db.scalars(
                select(Resource)
                .where(Resource.subject.is_not(None))
                .order_by(Resource.created_at.desc())
                .limit(RESOURCE_POOL * 4)
            )
        ).all()
    )

    def resource_rank(r: Resource) -> tuple[int, int, int]:
        exact = 0 if r.subject == subject else 1
        related = 0 if fields_compatible(r.subject, subject, min_score=0.75) else 1
        level_fit = 0 if r.education_level == level else 1
        return (exact, related, level_fit)

    # Prefer exact subject, then close relatives (e.g. calculus↔math), then level.
    ranked = sorted(resources, key=lambda r: (*resource_rank(r), -(r.download_count or 0)))
    matched_resources: list[Resource] = []
    for r in ranked:
        if r.subject == subject or fields_compatible(r.subject, subject, min_score=0.75):
            matched_resources.append(r)
        if len(matched_resources) >= RESOURCE_POOL:
            break

    if len(matched_resources) < MIN_RESOURCES_FOR_CONFIDENCE:
        for r in ranked:
            if r in matched_resources:
                continue
            if fields_compatible(r.subject, subject, min_score=0.6):
                matched_resources.append(r)
            if len(matched_resources) >= MIN_RESOURCES_FOR_CONFIDENCE:
                break

    if len(matched_resources) < 1:
        # Demo sparsity: same education level only as last resort.
        for r in ranked:
            if r.education_level == level and r not in matched_resources:
                matched_resources.append(r)
            if len(matched_resources) >= MIN_RESOURCES_FOR_CONFIDENCE:
                break

    techniques = list(
        (
            await db.scalars(
                select(Technique)
                .where(
                    Technique.is_published.is_(True),
                    Technique.is_draft.is_(False),
                )
                .order_by(Technique.average_rating.desc(), Technique.rating_count.desc())
                .limit(TECHNIQUE_POOL * 3)
            )
        ).all()
    )
    matched_techniques = [
        t
        for t in techniques
        if t.context_subject
        and (
            t.context_subject == subject
            or fields_compatible(t.context_subject, subject, min_score=0.75)
        )
    ][:TECHNIQUE_POOL]
    if len(matched_techniques) < 5:
        for t in techniques:
            if t not in matched_techniques and t.context_subject and fields_compatible(
                t.context_subject, subject, min_score=0.6
            ):
                matched_techniques.append(t)
            if len(matched_techniques) >= min(10, TECHNIQUE_POOL):
                break

    class_rows = list(
        (
            await db.scalars(
                select(ClassProfile)
                .where(ClassProfile.teacher_id != teacher_id)
                .order_by(ClassProfile.updated_at.desc())
                .limit(80)
            )
        ).all()
    )
    similar: list[ClassProfile] = []
    for row in class_rows:
        if exclude_class_id and row.id == exclude_class_id:
            continue
        if not fields_compatible(row.subject, subject, min_score=0.6):
            continue
        similar.append(row)
    similar.sort(
        key=lambda c: (
            0 if c.subject == subject else 1,
            0 if c.level == level else 1,
        )
    )
    similar = similar[:SIMILAR_CLASS_POOL]

    return RetrievalBundle(
        resources=matched_resources,
        techniques=matched_techniques,
        similar_classes=similar,
    )


def _validate_generated(
    generated: GeneratedCoursePlan,
    bundle: RetrievalBundle,
    *,
    expected_sessions: int | None = None,
) -> list[dict[str, Any]]:
    """Return normalised unit dicts or raise CoursePlanGenerationError."""
    if generated.cannot_generate:
        raise CoursePlanGenerationError(
            generated.cannot_generate_reason
            or "Not enough relevant resources to generate a grounded course plan.",
            resource_candidates=len(bundle.resources),
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    if len(bundle.resources) < 1:
        raise CoursePlanGenerationError(
            "Cannot confidently generate: no matching resources found in the library.",
            resource_candidates=0,
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    if not generated.units:
        raise CoursePlanGenerationError(
            "Cannot confidently generate: the model returned no units.",
            resource_candidates=len(bundle.resources),
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    resource_ids = {str(rid) for rid in bundle.resource_ids}
    technique_ids = {str(tid) for tid in bundle.technique_ids}
    normalised: list[dict[str, Any]] = []
    session_count = 0

    for unit in generated.units:
        title = (unit.title or "").strip()
        if not title:
            continue
        sessions_out: list[dict[str, Any]] = []
        for session in unit.sessions:
            stitle = (session.title or "").strip()
            if not stitle:
                continue
            items_out: list[dict[str, Any]] = []
            has_resource = False
            for item in session.items:
                rid = (item.resource_id or "").strip()
                tid = (item.technique_id or "").strip()
                role = (item.role or "core").strip().lower()
                if role not in ("core", "extension", "assessment"):
                    role = "core"
                valid_rid = rid if rid in resource_ids else None
                valid_tid = tid if tid in technique_ids else None
                if not valid_rid and not valid_tid:
                    continue
                if valid_rid:
                    has_resource = True
                items_out.append(
                    {
                        "role": role,
                        "resource_id": uuid.UUID(valid_rid) if valid_rid else None,
                        "technique_id": uuid.UUID(valid_tid) if valid_tid else None,
                    }
                )
            if not has_resource:
                raise CoursePlanGenerationError(
                    "Cannot confidently generate: every session must cite at least "
                    f"one existing resource (failed on session {stitle!r}).",
                    resource_candidates=len(bundle.resources),
                    technique_candidates=len(bundle.techniques),
                    similar_classes=len(bundle.similar_classes),
                )
            sessions_out.append(
                {
                    "title": stitle[:200],
                    "focus": (session.focus or "").strip() or None,
                    "activities_summary": (session.activities_summary or "").strip()
                    or None,
                    "items": items_out,
                }
            )
            session_count += 1
        if not sessions_out:
            continue
        labels = []
        for label in unit.concept_labels or []:
            cleaned = str(label).strip()
            if cleaned and cleaned not in labels:
                labels.append(cleaned[:120])
        normalised.append(
            {
                "title": title[:200],
                "objectives": (unit.objectives or "").strip() or None,
                "concept_labels": labels,
                "sessions": sessions_out,
            }
        )

    if not normalised:
        raise CoursePlanGenerationError(
            "Cannot confidently generate: no valid units after citation checks.",
            resource_candidates=len(bundle.resources),
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    if expected_sessions and session_count < max(1, expected_sessions // 3):
        # Soft warning path — still accept if citations are valid, but this
        # catches severely under-filled plans on dense briefs.
        logger.info(
            "Course plan produced %s sessions (expected ~%s)",
            session_count,
            expected_sessions,
        )

    return normalised


def _build_units(plan: CoursePlan, units_data: list[dict[str, Any]]) -> None:
    plan.units.clear()
    for u_idx, unit in enumerate(units_data):
        unit_row = CoursePlanUnit(
            position=u_idx,
            title=unit["title"],
            objectives=unit.get("objectives"),
            concept_labels=list(unit.get("concept_labels") or []),
        )
        for s_idx, session in enumerate(unit["sessions"]):
            session_row = CoursePlanSession(
                position=s_idx,
                title=session["title"],
                focus=session.get("focus"),
                activities_summary=session.get("activities_summary"),
            )
            for i_idx, item in enumerate(session["items"]):
                session_row.items.append(
                    CoursePlanItem(
                        position=i_idx,
                        role=item["role"],
                        resource_id=item.get("resource_id"),
                        technique_id=item.get("technique_id"),
                    )
                )
            unit_row.sessions.append(session_row)
        plan.units.append(unit_row)


def _units_from_input(units: list[CoursePlanUnitInput]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for unit in units:
        sessions: list[dict[str, Any]] = []
        for session in unit.sessions:
            items = [
                {
                    "role": item.role,
                    "resource_id": item.resource_id,
                    "technique_id": item.technique_id,
                }
                for item in session.items
            ]
            # Manual edits must also keep ≥1 resource per session.
            if not any(i["resource_id"] for i in items):
                raise CoursePlanGenerationError(
                    f"Session {session.title!r} must cite at least one resource."
                )
            sessions.append(
                {
                    "title": session.title,
                    "focus": session.focus,
                    "activities_summary": session.activities_summary,
                    "items": items,
                }
            )
        out.append(
            {
                "title": unit.title,
                "objectives": unit.objectives,
                "concept_labels": list(unit.concept_labels),
                "sessions": sessions,
            }
        )
    return out


def serialize_item(item: CoursePlanItem) -> CoursePlanItemRead:
    return CoursePlanItemRead(
        id=item.id,
        position=item.position,
        role=item.role,  # type: ignore[arg-type]
        resource_id=item.resource_id,
        technique_id=item.technique_id,
        resource_title=item.resource.title if item.resource else None,
        technique_title=item.technique.title if item.technique else None,
    )


def serialize_plan(
    plan: CoursePlan,
    *,
    similar_classes: list[ClassProfile] | None = None,
) -> CoursePlanRead:
    units = [
        CoursePlanUnitRead(
            id=unit.id,
            position=unit.position,
            title=unit.title,
            objectives=unit.objectives,
            concept_labels=list(unit.concept_labels or []),
            sessions=[
                CoursePlanSessionRead(
                    id=session.id,
                    position=session.position,
                    title=session.title,
                    focus=session.focus,
                    activities_summary=session.activities_summary,
                    items=[serialize_item(item) for item in session.items],
                )
                for session in session_list(unit)
            ],
        )
        for unit in sorted(plan.units, key=lambda u: u.position)
    ]
    similar_payload: list[dict[str, Any]] = []
    for klass in similar_classes or []:
        similar_payload.append(
            {
                "id": str(klass.id),
                "title": klass.title,
                "subject": klass.subject,
                "level": klass.level,
                "format": klass.format,
            }
        )
    return CoursePlanRead(
        id=plan.id,
        teacher_id=plan.teacher_id,
        class_profile_id=plan.class_profile_id,
        title=plan.title,
        subject=plan.subject,
        level=plan.level,
        format=plan.format,  # type: ignore[arg-type]
        status=plan.status,  # type: ignore[arg-type]
        duration_weeks=plan.duration_weeks,
        sessions_per_week=plan.sessions_per_week,
        goals=plan.goals,
        overview=plan.overview,
        constraints=plan.constraints,
        generation_inputs=dict(plan.generation_inputs or {}),
        similar_class_ids=list(plan.similar_class_ids or []),
        similar_classes=similar_payload,
        units=units,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def session_list(unit: CoursePlanUnit) -> list[CoursePlanSession]:
    return sorted(unit.sessions, key=lambda s: s.position)


def serialize_summary(plan: CoursePlan) -> CoursePlanSummary:
    return CoursePlanSummary(
        id=plan.id,
        teacher_id=plan.teacher_id,
        class_profile_id=plan.class_profile_id,
        title=plan.title,
        subject=plan.subject,
        level=plan.level,
        format=plan.format,  # type: ignore[arg-type]
        status=plan.status,  # type: ignore[arg-type]
        duration_weeks=plan.duration_weeks,
        sessions_per_week=plan.sessions_per_week,
        goals=plan.goals,
        overview=plan.overview,
        unit_count=len(plan.units or []),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


_PLAN_LOAD = (
    selectinload(CoursePlan.units)
    .selectinload(CoursePlanUnit.sessions)
    .selectinload(CoursePlanSession.items)
    .selectinload(CoursePlanItem.resource),
    selectinload(CoursePlan.units)
    .selectinload(CoursePlanUnit.sessions)
    .selectinload(CoursePlanSession.items)
    .selectinload(CoursePlanItem.technique),
)


async def get_owned_plan(
    db: AsyncSession, plan_id: uuid.UUID, teacher_id: uuid.UUID
) -> CoursePlan | None:
    return await db.scalar(
        select(CoursePlan)
        .where(CoursePlan.id == plan_id, CoursePlan.teacher_id == teacher_id)
        .options(*_PLAN_LOAD)
    )


async def list_plans(
    db: AsyncSession, teacher_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> list[CoursePlan]:
    return list(
        (
            await db.scalars(
                select(CoursePlan)
                .where(CoursePlan.teacher_id == teacher_id)
                .options(selectinload(CoursePlan.units))
                .order_by(CoursePlan.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )


async def _ensure_class_profile(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    payload: CoursePlanGenerateRequest,
) -> ClassProfile:
    if payload.class_profile_id:
        existing = await db.scalar(
            select(ClassProfile).where(
                ClassProfile.id == payload.class_profile_id,
                ClassProfile.teacher_id == teacher_id,
            )
        )
        if existing is None:
            raise CoursePlanGenerationError("Class profile not found.")
        return existing

    row = ClassProfile(
        teacher_id=teacher_id,
        title=payload.title,
        subject=payload.subject,
        level=payload.level,
        format=payload.format,
        status="planned",
        class_size=payload.class_size,
        class_size_min=payload.class_size_min,
        class_size_max=payload.class_size_max,
        student_background=payload.student_background,
        constraints=payload.constraints,
        class_length_minutes=payload.class_length_minutes,
        technology=payload.technology,
        notes=payload.notes
        or (
            f"Auto-created with course plan generator"
            f" ({payload.duration_weeks} weeks)."
        ),
    )
    db.add(row)
    await db.flush()
    return row


async def generate_plan(
    db: AsyncSession,
    teacher_id: uuid.UUID,
    payload: CoursePlanGenerateRequest,
) -> CoursePlan:
    if not llm_service.is_enabled():
        raise LLMUnavailable(
            "Generative features need LLM_API_KEY (an Anthropic API key)."
        )

    class_profile = await _ensure_class_profile(db, teacher_id, payload)
    bundle = await retrieve_candidates(
        db,
        teacher_id=teacher_id,
        subject=payload.subject,
        level=payload.level,
        exclude_class_id=class_profile.id,
    )

    if len(bundle.resources) < 1:
        raise CoursePlanGenerationError(
            "Cannot confidently generate: the library has no resources that "
            f"match {humanize(payload.subject)}. Add resources first, or try "
            "another subject.",
            resource_candidates=0,
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    brief = payload.model_dump(mode="json")
    try:
        generated = await llm_service.generate_course_plan_outline(
            brief=brief,
            resources=bundle.resources,
            techniques=bundle.techniques,
            similar_classes=bundle.similar_classes,
        )
    except LLMUnavailable:
        raise

    expected = payload.duration_weeks * payload.sessions_per_week
    units_data = _validate_generated(generated, bundle, expected_sessions=expected)

    plan = CoursePlan(
        teacher_id=teacher_id,
        class_profile_id=class_profile.id,
        title=generated.title.strip()[:200] or payload.title,
        subject=payload.subject,
        level=payload.level,
        format=payload.format,
        status="draft",
        duration_weeks=payload.duration_weeks,
        sessions_per_week=payload.sessions_per_week,
        goals=payload.goals,
        overview=(generated.overview or "").strip() or None,
        constraints=payload.constraints,
        generation_inputs=brief,
        similar_class_ids=[str(c.id) for c in bundle.similar_classes],
    )
    _build_units(plan, units_data)
    db.add(plan)
    await db.commit()

    loaded = await get_owned_plan(db, plan.id, teacher_id)
    assert loaded is not None
    return loaded


async def regenerate_plan(
    db: AsyncSession,
    plan: CoursePlan,
    overrides: CoursePlanRegenerateRequest | None = None,
) -> CoursePlan:
    if not llm_service.is_enabled():
        raise LLMUnavailable(
            "Generative features need LLM_API_KEY (an Anthropic API key)."
        )

    overrides = overrides or CoursePlanRegenerateRequest()
    if overrides.duration_weeks is not None:
        plan.duration_weeks = overrides.duration_weeks
    if overrides.sessions_per_week is not None:
        plan.sessions_per_week = overrides.sessions_per_week
    if overrides.goals is not None:
        plan.goals = overrides.goals
    if overrides.constraints is not None:
        plan.constraints = overrides.constraints

    brief = dict(plan.generation_inputs or {})
    brief.update(
        {
            "title": plan.title,
            "subject": plan.subject,
            "level": plan.level,
            "format": plan.format,
            "duration_weeks": plan.duration_weeks,
            "sessions_per_week": plan.sessions_per_week,
            "goals": plan.goals,
            "constraints": plan.constraints,
        }
    )
    if overrides.topic_hints is not None:
        brief["topic_hints"] = overrides.topic_hints

    bundle = await retrieve_candidates(
        db,
        teacher_id=plan.teacher_id,
        subject=plan.subject,
        level=plan.level,
        exclude_class_id=plan.class_profile_id,
    )
    if len(bundle.resources) < 1:
        raise CoursePlanGenerationError(
            "Cannot confidently regenerate: no matching resources in the library.",
            resource_candidates=0,
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    generated = await llm_service.generate_course_plan_outline(
        brief=brief,
        resources=bundle.resources,
        techniques=bundle.techniques,
        similar_classes=bundle.similar_classes,
        existing_overview=plan.overview,
    )
    expected = plan.duration_weeks * plan.sessions_per_week
    units_data = _validate_generated(generated, bundle, expected_sessions=expected)

    if generated.title.strip():
        plan.title = generated.title.strip()[:200]
    plan.overview = (generated.overview or "").strip() or plan.overview
    plan.generation_inputs = brief
    plan.similar_class_ids = [str(c.id) for c in bundle.similar_classes]
    _build_units(plan, units_data)
    await db.commit()

    loaded = await get_owned_plan(db, plan.id, plan.teacher_id)
    assert loaded is not None
    return loaded


async def regenerate_unit(
    db: AsyncSession, plan: CoursePlan, unit_id: uuid.UUID
) -> CoursePlan:
    if not llm_service.is_enabled():
        raise LLMUnavailable(
            "Generative features need LLM_API_KEY (an Anthropic API key)."
        )

    ordered = sorted(plan.units, key=lambda u: u.position)
    target = next((u for u in ordered if u.id == unit_id), None)
    if target is None:
        raise CoursePlanGenerationError("Unit not found on this plan.")
    target_index = ordered.index(target)

    brief = dict(plan.generation_inputs or {})
    brief.update(
        {
            "title": plan.title,
            "subject": plan.subject,
            "level": plan.level,
            "format": plan.format,
            "duration_weeks": plan.duration_weeks,
            "sessions_per_week": plan.sessions_per_week,
            "goals": plan.goals,
            "constraints": plan.constraints,
        }
    )
    bundle = await retrieve_candidates(
        db,
        teacher_id=plan.teacher_id,
        subject=plan.subject,
        level=plan.level,
        exclude_class_id=plan.class_profile_id,
    )
    if len(bundle.resources) < 1:
        raise CoursePlanGenerationError(
            "Cannot confidently regenerate: no matching resources in the library.",
            resource_candidates=0,
            technique_candidates=len(bundle.techniques),
            similar_classes=len(bundle.similar_classes),
        )

    generated = await llm_service.generate_course_plan_outline(
        brief=brief,
        resources=bundle.resources,
        techniques=bundle.techniques,
        similar_classes=bundle.similar_classes,
        existing_overview=plan.overview,
        unit_focus={
            "position": target.position,
            "title": target.title,
            "objectives": target.objectives,
        },
    )
    units_data = _validate_generated(generated, bundle)
    new_unit = units_data[0]

    # Preserve sibling units; swap only the regenerated one.
    rebuilt: list[dict[str, Any]] = []
    for idx, unit in enumerate(ordered):
        if idx == target_index:
            rebuilt.append(new_unit)
            continue
        sessions = []
        for session in session_list(unit):
            sessions.append(
                {
                    "title": session.title,
                    "focus": session.focus,
                    "activities_summary": session.activities_summary,
                    "items": [
                        {
                            "role": item.role,
                            "resource_id": item.resource_id,
                            "technique_id": item.technique_id,
                        }
                        for item in sorted(session.items, key=lambda i: i.position)
                    ],
                }
            )
        rebuilt.append(
            {
                "title": unit.title,
                "objectives": unit.objectives,
                "concept_labels": list(unit.concept_labels or []),
                "sessions": sessions,
            }
        )

    _build_units(plan, rebuilt)
    await db.commit()

    loaded = await get_owned_plan(db, plan.id, plan.teacher_id)
    assert loaded is not None
    return loaded


async def update_metadata(
    db: AsyncSession, plan: CoursePlan, payload: CoursePlanUpdate
) -> CoursePlan:
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)
    await db.commit()
    loaded = await get_owned_plan(db, plan.id, plan.teacher_id)
    assert loaded is not None
    return loaded


async def replace_structure(
    db: AsyncSession, plan: CoursePlan, payload: CoursePlanStructureUpdate
) -> CoursePlan:
    units_data = _units_from_input(payload.units)
    if payload.overview is not None:
        plan.overview = payload.overview
    _build_units(plan, units_data)
    await db.commit()
    loaded = await get_owned_plan(db, plan.id, plan.teacher_id)
    assert loaded is not None
    return loaded


async def delete_plan(db: AsyncSession, plan: CoursePlan) -> None:
    await db.delete(plan)
    await db.commit()


async def load_similar_classes(
    db: AsyncSession, ids: list[str]
) -> list[ClassProfile]:
    if not ids:
        return []
    parsed: list[uuid.UUID] = []
    for raw in ids:
        try:
            parsed.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    if not parsed:
        return []
    rows = list(
        (await db.scalars(select(ClassProfile).where(ClassProfile.id.in_(parsed)))).all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in parsed if i in by_id]
