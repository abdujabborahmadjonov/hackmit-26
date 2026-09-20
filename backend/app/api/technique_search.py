"""Parse, refine, and run class-scoped technique search; planning mode."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.techniques import _technique_read
from app.database import get_db
from app.models.class_profile import ClassProfile
from app.models.concept import Concept
from app.schemas.technique import (
    ConceptChip,
    FollowUpOption,
    PitfallItem,
    PlanningResponse,
    TechniqueSearchParseRequest,
    TechniqueSearchParseResponse,
    TechniqueSearchRefineRequest,
    TechniqueSearchRunRequest,
    TechniqueSearchRunResponse,
)
from app.services import llm_service
from app.services.llm_service import LLMUnavailable
from app.services.technique_search_service import (
    PROBLEM_TYPE_LABELS,
    load_ratings_for,
    planning_pitfalls,
    search_techniques,
)
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/technique-search", tags=["technique-search"])
DB = Annotated[AsyncSession, Depends(get_db)]
ai_rate_limit = RateLimiter("ai", 30)

PROBLEM_TYPE_EXAMPLES = {
    "misconception": "Students think force is required to keep an object moving (physics)",
    "missing_prerequisite": "Can't factor quadratics because fraction arithmetic is shaky (algebra)",
    "engagement": "Half the lab checks out after the first 10 minutes of demo (chemistry)",
    "pacing": "Finishers wait 15 minutes while others are still on step 2 (CS lab)",
    "transfer": "Solves worksheet problems but freezes on a worded exam variant (stats)",
}

VAGUE_VS_SPECIFIC = (
    'Vague: "students struggle with this." '
    'Specific: "they treat derivatives as fractions and cancel dy/dx symbols."'
)


async def _owned_class(
    db: AsyncSession, class_id: uuid.UUID, teacher_id: uuid.UUID
) -> ClassProfile:
    row = await db.scalar(
        select(ClassProfile).where(
            ClassProfile.id == class_id,
            ClassProfile.teacher_id == teacher_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class profile not found")
    return row


def _heuristic_parse(
    concept_text: str, problem_text: str
) -> TechniqueSearchParseResponse:
    """Offline fallback when LLM is unavailable."""
    broad = concept_text.strip().lower() in {
        "math",
        "mathematics",
        "science",
        "biology",
        "chemistry",
        "physics",
        "cs",
        "computer science",
        "english",
        "history",
    }
    vague = len(problem_text.strip()) < 40 or problem_text.strip().lower() in {
        "students struggle",
        "it's hard",
        "its hard",
        "they don't get it",
        "they dont get it",
        "confused",
    }

    if broad:
        options = [
            FollowUpOption(id=s, label=s, example=None)
            for s in [
                "Limits and continuity",
                "Derivatives as rates",
                "Chain rule",
                "Related rates",
                "Optimization",
            ]
        ]
        return TechniqueSearchParseResponse(
            concept_chips=[],
            problem_chips=[problem_text.strip()] if problem_text.strip() else [],
            problem_types=[],
            needs_follow_up=True,
            follow_up_kind="concept",
            follow_up_prompt="That concept is broad — pick a more specific focus:",
            follow_up_options=options,
            vague_vs_specific=VAGUE_VS_SPECIFIC,
            round=0,
        )

    if vague:
        options = [
            FollowUpOption(
                id=ptype,
                label=PROBLEM_TYPE_LABELS[ptype],
                example=PROBLEM_TYPE_EXAMPLES[ptype],
            )
            for ptype in PROBLEM_TYPE_EXAMPLES
        ]
        return TechniqueSearchParseResponse(
            concept_chips=[ConceptChip(label=concept_text.strip())],
            problem_chips=[],
            problem_types=[],
            needs_follow_up=True,
            follow_up_kind="problem",
            follow_up_prompt="What kind of problem are you seeing?",
            follow_up_options=options,
            vague_vs_specific=VAGUE_VS_SPECIFIC,
            round=0,
        )

    return TechniqueSearchParseResponse(
        concept_chips=[ConceptChip(label=concept_text.strip())],
        problem_chips=[problem_text.strip()],
        problem_types=[],
        needs_follow_up=False,
        follow_up_kind="none",
        vague_vs_specific=VAGUE_VS_SPECIFIC,
        round=0,
    )


@router.post(
    "/parse",
    response_model=TechniqueSearchParseResponse,
    dependencies=[Depends(ai_rate_limit)],
)
async def parse_search(
    payload: TechniqueSearchParseRequest,
    current_user: CurrentUser,
    db: DB,
) -> TechniqueSearchParseResponse:
    klass = await _owned_class(db, payload.class_profile_id, current_user.id)

    if not llm_service.is_enabled():
        return _heuristic_parse(payload.concept_text, payload.problem_text)

    try:
        parsed = await llm_service.parse_technique_search(
            concept_text=payload.concept_text,
            problem_text=payload.problem_text,
            class_subject=klass.subject,
            class_level=klass.level,
            round_number=payload.round,
        )
    except LLMUnavailable:
        return _heuristic_parse(payload.concept_text, payload.problem_text)

    # Prefer concept follow-up over problem when both fire and rounds remain.
    if parsed.concept_too_broad and payload.round < 2:
        options = [
            FollowUpOption(id=s, label=s)
            for s in (parsed.suggested_subconcepts or [])[:6]
        ]
        return TechniqueSearchParseResponse(
            concept_chips=[],
            problem_chips=[payload.problem_text.strip()],
            problem_types=[],
            needs_follow_up=True,
            follow_up_kind="concept",
            follow_up_prompt=parsed.follow_up_prompt
            or "That concept is broad — pick a more specific focus:",
            follow_up_options=options,
            vague_vs_specific=parsed.vague_vs_specific or VAGUE_VS_SPECIFIC,
            round=payload.round,
        )

    if parsed.problem_too_vague and payload.round < 2:
        suggested = parsed.suggested_problem_types or list(PROBLEM_TYPE_EXAMPLES)
        options = [
            FollowUpOption(
                id=ptype,
                label=PROBLEM_TYPE_LABELS.get(ptype, ptype),
                example=PROBLEM_TYPE_EXAMPLES.get(ptype),
            )
            for ptype in suggested
            if ptype in PROBLEM_TYPE_EXAMPLES
        ]
        return TechniqueSearchParseResponse(
            concept_chips=[ConceptChip(label=label) for label in parsed.concept_labels]
            or [ConceptChip(label=payload.concept_text.strip())],
            problem_chips=[],
            problem_types=[],
            needs_follow_up=True,
            follow_up_kind="problem",
            follow_up_prompt=parsed.follow_up_prompt
            or "What kind of problem are you seeing?",
            follow_up_options=options,
            vague_vs_specific=parsed.vague_vs_specific or VAGUE_VS_SPECIFIC,
            round=payload.round,
        )

    valid_types = [
        p
        for p in parsed.problem_types
        if p in PROBLEM_TYPE_EXAMPLES
    ]
    return TechniqueSearchParseResponse(
        concept_chips=[ConceptChip(label=label) for label in parsed.concept_labels]
        or [ConceptChip(label=payload.concept_text.strip())],
        problem_chips=[parsed.problem_summary or payload.problem_text.strip()],
        problem_types=valid_types,  # type: ignore[arg-type]
        needs_follow_up=False,
        follow_up_kind="none",
        vague_vs_specific=parsed.vague_vs_specific or VAGUE_VS_SPECIFIC,
        round=payload.round,
    )


@router.post("/refine", response_model=TechniqueSearchParseResponse)
async def refine_search(
    payload: TechniqueSearchRefineRequest,
    current_user: CurrentUser,
    db: DB,
) -> TechniqueSearchParseResponse:
    await _owned_class(db, payload.class_profile_id, current_user.id)

    concept_chips = list(payload.concept_chips)
    problem_chips = list(payload.problem_chips)
    problem_types = list(payload.problem_types)

    for opt_id in payload.selected_option_ids:
        if opt_id in PROBLEM_TYPE_EXAMPLES:
            if opt_id not in problem_types:
                problem_types.append(opt_id)  # type: ignore[arg-type]
        else:
            # Treat as a concept label from a concept follow-up.
            if not any(c.label == opt_id for c in concept_chips):
                concept_chips.append(ConceptChip(label=opt_id))

    # One more round max if still empty.
    needs = False
    kind: str = "none"
    options: list[FollowUpOption] = []
    prompt = None
    if not concept_chips and payload.round < 2:
        needs = True
        kind = "concept"
        prompt = "Pick at least one specific concept:"
        options = [
            FollowUpOption(id=s, label=s)
            for s in ["Core idea A", "Core idea B", "Core idea C"]
        ]
    elif not problem_types and not problem_chips and payload.round < 2:
        needs = True
        kind = "problem"
        prompt = "What kind of problem are you seeing?"
        options = [
            FollowUpOption(
                id=ptype,
                label=PROBLEM_TYPE_LABELS[ptype],
                example=PROBLEM_TYPE_EXAMPLES[ptype],
            )
            for ptype in PROBLEM_TYPE_EXAMPLES
        ]

    return TechniqueSearchParseResponse(
        concept_chips=concept_chips,
        problem_chips=problem_chips,
        problem_types=problem_types,
        needs_follow_up=needs,
        follow_up_kind=kind,  # type: ignore[arg-type]
        follow_up_prompt=prompt,
        follow_up_options=options,
        vague_vs_specific=VAGUE_VS_SPECIFIC,
        round=payload.round,
    )


@router.post("/run", response_model=TechniqueSearchRunResponse)
async def run_search(
    payload: TechniqueSearchRunRequest,
    current_user: CurrentUser,
    db: DB,
) -> TechniqueSearchRunResponse:
    klass = await _owned_class(db, payload.class_profile_id, current_user.id)
    scored = await search_techniques(
        db,
        searcher=klass,
        concept_ids=payload.concept_ids,
        concept_labels=payload.concept_labels,
        problem_types=list(payload.problem_types),
        problem_text=payload.problem_text,
        limit=payload.limit,
    )
    await db.commit()  # persist any newly canonicalized concepts

    ratings_map = await load_ratings_for(db, [s.technique.id for s in scored])
    items = [
        _technique_read(
            s.technique,
            ratings=ratings_map.get(s.technique.id, []),
            searcher=klass,
            score=round(s.score, 4),
            breakdown=s.breakdown,
        )
        for s in scored
    ]
    return TechniqueSearchRunResponse(
        items=items,
        query_concepts=[ConceptChip(label=label) for label in payload.concept_labels]
        + [ConceptChip(id=cid, label=str(cid)) for cid in payload.concept_ids],
        problem_types=payload.problem_types,
    )


@router.get("/planning", response_model=PlanningResponse)
async def planning_mode(
    current_user: CurrentUser,
    db: DB,
    class_profile_id: Annotated[uuid.UUID, Query()],
    concept_id: Annotated[uuid.UUID | None, Query()] = None,
    concept_label: Annotated[str | None, Query(max_length=200)] = None,
) -> PlanningResponse:
    klass = await _owned_class(db, class_profile_id, current_user.id)

    concept: Concept | None = None
    if concept_id:
        concept = await db.scalar(select(Concept).where(Concept.id == concept_id))
    elif concept_label:
        from app.services import concept_service

        concept = await concept_service.canonicalize(
            db, label=concept_label, subject=klass.subject, use_llm_borderline=False
        )
        await db.commit()

    if concept is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide concept_id or concept_label",
        )

    pitfalls_raw = await planning_pitfalls(db, searcher=klass, concept=concept)
    ratings_map = await load_ratings_for(
        db,
        [t.technique.id for p in pitfalls_raw for t in p["top"]],
    )
    pitfalls = [
        PitfallItem(
            problem_type=p["problem_type"],
            label=p["label"],
            report_count=p["report_count"],
            top_techniques=[
                _technique_read(
                    s.technique,
                    ratings=ratings_map.get(s.technique.id, []),
                    searcher=klass,
                    score=round(s.score, 4),
                    breakdown=s.breakdown,
                )
                for s in p["top"]
            ],
        )
        for p in pitfalls_raw
    ]
    return PlanningResponse(
        class_profile_id=klass.id,
        concept=ConceptChip(
            id=concept.id, label=concept.label, slug=concept.slug, subject=concept.subject
        ),
        pitfalls=pitfalls,
    )
