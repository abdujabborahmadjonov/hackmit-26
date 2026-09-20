"""Technique retrieval, Bayesian/class-weighted scoring, and MMR re-ranking."""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.class_profile import ClassProfile
from app.models.concept import Concept
from app.models.technique import Technique, TechniqueConcept, TechniqueRating
from app.services.embedding_service import cosine_similarity, get_embedding_service
from app.services import concept_service
from app.taxonomy import (
    CLOSE_FIELD_THRESHOLD,
    canonical_term,
    fields_compatible,
    term_relatedness,
)

logger = logging.getLogger(__name__)

# Bayesian prior: weak prior toward the global mean so unrated items don't dominate.
BAYESIAN_M = 8.0
GLOBAL_PRIOR = 3.6

PROBLEM_TYPE_LABELS = {
    "misconception": "Misconception",
    "missing_prerequisite": "Missing prerequisite",
    "engagement": "Engagement",
    "pacing": "Pacing",
    "transfer": "Transfer",
}


@dataclass
class ScoredTechnique:
    technique: Technique
    score: float
    breakdown: dict[str, float]


def class_context_similarity(
    searcher: ClassProfile,
    *,
    subject: str | None,
    level: str | None,
    format_: str | None,
    class_size: float | None,
) -> float:
    """0-1 similarity between the searcher's class and a rating/technique context."""
    parts: list[float] = []

    if subject and searcher.subject:
        parts.append(_subject_similarity(searcher.subject, subject))
    if level and searcher.level:
        parts.append(1.0 if _norm(level) == _norm(searcher.level) else 0.35)
    if format_ and searcher.format:
        parts.append(1.0 if format_ == searcher.format else 0.4)

    searcher_size = searcher.effective_class_size()
    if class_size and searcher_size:
        ratio = min(class_size, searcher_size) / max(class_size, searcher_size)
        parts.append(ratio)

    if not parts:
        return 0.5
    return sum(parts) / len(parts)


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _subject_similarity(searcher_subject: str, other: str) -> float:
    """Exact / closely related subjects score high; unrelated near zero."""
    a = canonical_term(searcher_subject)
    b = canonical_term(other)
    if a == b:
        return 1.0
    related = term_relatedness(a, b)
    if related >= CLOSE_FIELD_THRESHOLD:
        return 0.65 + 0.35 * related
    if fields_compatible(a, b):
        return 0.7
    return 0.05


def technique_field_subjects(technique: Technique) -> list[str]:
    """Subjects attached to a technique via context and linked concepts."""
    subjects: list[str] = []
    if technique.context_subject:
        subjects.append(technique.context_subject)
    for link in technique.concepts or []:
        concept = getattr(link, "concept", None)
        if concept is not None and getattr(concept, "subject", None):
            subjects.append(concept.subject)
    return subjects


def technique_matches_field(technique: Technique, searcher_subject: str) -> bool:
    """Hard gate: technique must share the searcher's field or a close neighbor."""
    subjects = technique_field_subjects(technique)
    if not subjects:
        return False
    return any(fields_compatible(searcher_subject, subject) for subject in subjects)


def problem_type_overlap(wanted: list[str], have: list[str] | None) -> float:
    if not wanted:
        return 0.5
    have_set = set(have or [])
    if not have_set:
        return 0.15
    hits = len(have_set.intersection(wanted))
    return hits / len(wanted)


def bayesian_average(ratings: list[tuple[int, float]], *, prior: float = GLOBAL_PRIOR, m: float = BAYESIAN_M) -> float:
    """Weighted Bayesian average; each rating carries a class-similarity weight."""
    if not ratings:
        return prior
    weight_sum = sum(max(0.05, w) for _, w in ratings)
    score_sum = sum(r * max(0.05, w) for r, w in ratings)
    return (m * prior + score_sum) / (m + weight_sum)


def mmr_rerank(
    candidates: list[ScoredTechnique],
    *,
    lambda_: float = 0.7,
    limit: int = 10,
) -> list[ScoredTechnique]:
    """Maximal Marginal Relevance over teaching_style embeddings / labels."""
    if not candidates:
        return []

    selected: list[ScoredTechnique] = []
    remaining = list(candidates)

    while remaining and len(selected) < limit:
        best_idx = 0
        best_val = -1e9
        for idx, cand in enumerate(remaining):
            relevance = cand.score
            diversity_pen = 0.0
            if selected:
                diversity_pen = max(
                    _style_similarity(cand.technique, other.technique) for other in selected
                )
            value = lambda_ * relevance - (1 - lambda_) * diversity_pen
            if value > best_val:
                best_val = value
                best_idx = idx
        selected.append(remaining.pop(best_idx))
    return selected


def _style_similarity(a: Technique, b: Technique) -> float:
    # pgvector returns ndarray; never use truthiness on embeddings.
    if a.embedding is not None and b.embedding is not None:
        return max(0.0, cosine_similarity(list(a.embedding), list(b.embedding)))
    if a.teaching_style and b.teaching_style:
        return 1.0 if _norm(a.teaching_style) == _norm(b.teaching_style) else 0.2
    return 0.1


async def resolve_concepts(
    db: AsyncSession,
    *,
    concept_ids: list[uuid.UUID],
    concept_labels: list[str],
    subject: str,
) -> list[Concept]:
    concepts: list[Concept] = []
    seen: set[uuid.UUID] = set()
    if concept_ids:
        rows = (
            await db.scalars(select(Concept).where(Concept.id.in_(concept_ids)))
        ).all()
        for row in rows:
            if row.id not in seen:
                seen.add(row.id)
                concepts.append(row)
    for label in concept_labels:
        concept = await concept_service.canonicalize(
            db, label=label, subject=subject, use_llm_borderline=False
        )
        if concept.id not in seen:
            seen.add(concept.id)
            concepts.append(concept)
    return concepts


async def retrieve_candidates(
    db: AsyncSession,
    *,
    concepts: list[Concept],
    problem_text: str | None,
    searcher_subject: str,
    limit: int = 80,
) -> list[Technique]:
    concept_ids = [c.id for c in concepts]
    found: dict[uuid.UUID, Technique] = {}

    if concept_ids:
        rows = (
            await db.scalars(
                select(Technique)
                .join(TechniqueConcept, TechniqueConcept.technique_id == Technique.id)
                .where(
                    TechniqueConcept.concept_id.in_(concept_ids),
                    Technique.is_published.is_(True),
                    Technique.is_draft.is_(False),
                )
                .options(selectinload(Technique.concepts).selectinload(TechniqueConcept.concept))
                .limit(limit * 3)
            )
        ).all()
        for row in rows:
            if technique_matches_field(row, searcher_subject):
                found[row.id] = row

    # Embedding fallback when concept join is thin — still field-gated.
    if len(found) < max(8, limit // 4):
        query_text = " ".join(c.label for c in concepts)
        if problem_text:
            query_text = f"{query_text} {problem_text}"
        if query_text.strip():
            vector = (await get_embedding_service().generate_embeddings([query_text]))[0]
            # Pull a larger published pool and score in Python (hashing provider friendly).
            pool = (
                await db.scalars(
                    select(Technique)
                    .where(
                        Technique.is_published.is_(True),
                        Technique.is_draft.is_(False),
                        Technique.embedding.is_not(None),
                    )
                    .options(
                        selectinload(Technique.concepts).selectinload(TechniqueConcept.concept)
                    )
                    .limit(500)
                )
            ).all()
            scored = []
            for tech in pool:
                if tech.embedding is None:
                    continue
                if not technique_matches_field(tech, searcher_subject):
                    continue
                sim = cosine_similarity(vector, list(tech.embedding))
                scored.append((sim, tech))
            scored.sort(key=lambda item: item[0], reverse=True)
            for _, tech in scored[:limit]:
                found.setdefault(tech.id, tech)

    return list(found.values())[:limit]


async def load_ratings_for(
    db: AsyncSession, technique_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[TechniqueRating]]:
    if not technique_ids:
        return {}
    rows = (
        await db.scalars(
            select(TechniqueRating).where(TechniqueRating.technique_id.in_(technique_ids))
        )
    ).all()
    out: dict[uuid.UUID, list[TechniqueRating]] = {tid: [] for tid in technique_ids}
    for row in rows:
        out.setdefault(row.technique_id, []).append(row)
    return out


def score_technique(
    technique: Technique,
    *,
    searcher: ClassProfile,
    problem_types: list[str],
    ratings: list[TechniqueRating],
) -> ScoredTechnique:
    context_fit = class_context_similarity(
        searcher,
        subject=technique.context_subject,
        level=technique.context_level,
        format_=technique.context_format,
        class_size=float(technique.context_class_size)
        if technique.context_class_size
        else None,
    )
    problem_fit = problem_type_overlap(problem_types, technique.problem_types)

    weighted = [
        (
            r.rating,
            class_context_similarity(
                searcher,
                subject=r.context_subject,
                level=r.context_level,
                format_=r.context_format,
                class_size=float(r.context_class_size) if r.context_class_size else None,
            ),
        )
        for r in ratings
    ]
    quality = bayesian_average(weighted)
    quality_norm = (quality - 1.0) / 4.0  # map 1-5 -> 0-1

    # Blend: field/context fit is the strongest signal for classroom match.
    score = 0.45 * context_fit + 0.25 * problem_fit + 0.30 * quality_norm
    return ScoredTechnique(
        technique=technique,
        score=score,
        breakdown={
            "context_fit": round(context_fit, 4),
            "problem_fit": round(problem_fit, 4),
            "quality": round(quality_norm, 4),
            "bayesian_rating": round(quality, 3),
        },
    )


def rating_summary_for(
    ratings: list[TechniqueRating],
    *,
    searcher: ClassProfile | None = None,
) -> dict:
    distribution = {str(i): 0 for i in range(1, 6)}
    for row in ratings:
        distribution[str(row.rating)] = distribution.get(str(row.rating), 0) + 1

    if ratings:
        if searcher is not None:
            weighted = [
                (
                    r.rating,
                    class_context_similarity(
                        searcher,
                        subject=r.context_subject,
                        level=r.context_level,
                        format_=r.context_format,
                        class_size=float(r.context_class_size) if r.context_class_size else None,
                    ),
                )
                for r in ratings
            ]
            average = bayesian_average(weighted)
            similar = sum(1 for _, w in weighted if w >= 0.6)
        else:
            average = sum(r.rating for r in ratings) / len(ratings)
            similar = len(ratings)
        comments = [r.comment for r in ratings if r.comment]
        sample = comments[0] if comments else None
    else:
        average = 0.0
        similar = 0
        sample = None

    return {
        "average": round(average, 2),
        "count": len(ratings),
        "distribution": distribution,
        "similar_class_count": similar,
        "sample_comment": sample,
    }


async def search_techniques(
    db: AsyncSession,
    *,
    searcher: ClassProfile,
    concept_ids: list[uuid.UUID],
    concept_labels: list[str],
    problem_types: list[str],
    problem_text: str | None = None,
    limit: int = 10,
) -> list[ScoredTechnique]:
    concepts = await resolve_concepts(
        db,
        concept_ids=concept_ids,
        concept_labels=concept_labels,
        subject=searcher.subject,
    )
    candidates = await retrieve_candidates(
        db,
        concepts=concepts,
        problem_text=problem_text,
        searcher_subject=searcher.subject,
        limit=80,
    )
    # Final hard gate in case any candidate slipped through without subject metadata.
    candidates = [c for c in candidates if technique_matches_field(c, searcher.subject)]
    ratings_map = await load_ratings_for(db, [c.id for c in candidates])

    scored = [
        score_technique(
            tech,
            searcher=searcher,
            problem_types=problem_types,
            ratings=ratings_map.get(tech.id, []),
        )
        for tech in candidates
    ]
    scored.sort(key=lambda item: item.score, reverse=True)

    # Reserve one slot for a new/unrated technique before MMR.
    unrated = [s for s in scored if s.technique.rating_count == 0]
    reranked = mmr_rerank(scored, limit=max(limit - (1 if unrated else 0), 1))

    if unrated:
        pick = unrated[0]
        if all(item.technique.id != pick.technique.id for item in reranked):
            if len(reranked) >= limit:
                reranked = reranked[: limit - 1]
            reranked.append(pick)

    return reranked[:limit]


async def planning_pitfalls(
    db: AsyncSession,
    *,
    searcher: ClassProfile,
    concept: Concept,
    limit_per: int = 3,
) -> list[dict]:
    """Aggregate problem types seen for a concept in similar contexts."""
    techniques = (
        await db.scalars(
            select(Technique)
            .join(TechniqueConcept, TechniqueConcept.technique_id == Technique.id)
            .where(
                TechniqueConcept.concept_id == concept.id,
                Technique.is_published.is_(True),
            )
            .options(selectinload(Technique.concepts).selectinload(TechniqueConcept.concept))
        )
    ).all()

    counter: Counter[str] = Counter()
    by_type: dict[str, list[Technique]] = {}
    for tech in techniques:
        if not technique_matches_field(tech, searcher.subject):
            continue
        for ptype in tech.problem_types or []:
            counter[ptype] += 1
            by_type.setdefault(ptype, []).append(tech)

    ratings_map = await load_ratings_for(db, [t.id for t in techniques])
    pitfalls = []
    for ptype, count in counter.most_common():
        scored = [
            score_technique(
                tech,
                searcher=searcher,
                problem_types=[ptype],
                ratings=ratings_map.get(tech.id, []),
            )
            for tech in by_type.get(ptype, [])
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        pitfalls.append(
            {
                "problem_type": ptype,
                "label": PROBLEM_TYPE_LABELS.get(ptype, ptype),
                "report_count": count,
                "top": scored[:limit_per],
            }
        )
    return pitfalls


def technique_embedding_text(technique: Technique) -> str:
    parts = [
        technique.title,
        technique.summary,
        technique.steps,
        technique.materials or "",
        technique.teaching_style or "",
        " ".join(technique.problem_types or []),
        technique.context_subject or "",
        technique.context_notes or "",
    ]
    return "\n".join(p for p in parts if p)


async def refresh_technique_embedding(db: AsyncSession, technique: Technique) -> None:
    vector = (await get_embedding_service().generate_embeddings([technique_embedding_text(technique)]))[0]
    technique.embedding = vector
    await db.flush()


async def recompute_technique_rating_aggregates(
    db: AsyncSession, technique_id: uuid.UUID
) -> Technique:
    tech = await db.scalar(select(Technique).where(Technique.id == technique_id))
    if tech is None:
        raise ValueError("Technique not found")
    rows = (
        await db.scalars(
            select(TechniqueRating).where(TechniqueRating.technique_id == technique_id)
        )
    ).all()
    if not rows:
        tech.average_rating = 0.0
        tech.rating_count = 0
    else:
        tech.average_rating = sum(r.rating for r in rows) / len(rows)
        tech.rating_count = len(rows)
    await db.flush()
    return tech
