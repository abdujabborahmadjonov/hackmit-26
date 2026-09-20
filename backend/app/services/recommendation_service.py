"""The hybrid recommendation engine - EduMatch's core feature.

Scoring (weights configurable via REC_WEIGHT_* env vars; also bandit / profile):

    score = w_semantic * semantic teaching-style similarity
          + w_expertise * subject / expertise similarity
          + w_education * education-level compatibility
          + w_teaching_level * teaching-level compatibility
          + w_location * geographic proximity
          + w_class_size * class-size similarity
          + w_social * friends-of-friends / shared connections
          + w_quality * Bayesian peer rating quality

Performance: embeddings are written when a profile changes, never at request
time. A request does one ANN query against the pgvector HNSW index plus one
structured overlap query, then scores only that candidate pool in Python.
Optional MMR diversifies the final top-N.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import normalise_recommendation_weights, settings
from app.models.connection import Connection, ConnectionStatus
from app.models.profile import TeacherProfile
from app.models.recommendation import RecommendationEvent
from app.models.resource import Resource
from app.models.user import User
from app.services import bandit_service
from app.services.embedding_service import cosine_similarity
from app.services.relatedness_service import combined_relatedness, ensure_cooccurrence
from app.taxonomy import (
    TEACHING_LEVELS,
    canonical_terms,
    education_compatibility,
    humanize,
)
from app.utils.geo import location_similarity

logger = logging.getLogger(__name__)


class ProfileRequiredError(RuntimeError):
    """Raised when a user asks for recommendations without a profile."""


# --------------------------------------------------------------------------- #
# Pure scoring functions (unit tested in tests/test_scoring.py)
# --------------------------------------------------------------------------- #
def semantic_similarity(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity of the two teaching-style vectors, clamped to [0, 1]."""
    return cosine_similarity(a, b)


def expertise_similarity(a_terms: list[str] | None, b_terms: list[str] | None) -> float:
    """Soft Jaccard over subjects + fields of expertise.

    Identical terms score 1.0, related terms (ML <-> AI, hand or co-occurrence)
    score partially.
    """
    a = canonical_terms(a_terms)
    b = canonical_terms(b_terms)
    if not a or not b:
        return 0.0

    matched = 0.0
    for term in a:
        best = max((combined_relatedness(term, other) for other in b), default=0.0)
        matched += best
    for term in b:
        best = max((combined_relatedness(term, other) for other in a), default=0.0)
        matched += best

    union_size = len(a) + len(b)
    return max(0.0, min(1.0, matched / union_size))


def education_similarity(
    a_levels: list[str] | None,
    b_levels: list[str] | None,
    overrides: dict[str, dict[str, float]] | None = None,
) -> float:
    """Best compatibility across the two sets of education levels."""
    if not a_levels or not b_levels:
        return 0.0
    return max(
        education_compatibility(a, b, overrides) for a in a_levels for b in b_levels
    )


def teaching_level_similarity(a_levels: list[str] | None, b_levels: list[str] | None) -> float:
    """Proximity on the beginner -> intermediate -> advanced ladder."""
    if not a_levels or not b_levels:
        return 0.0
    span = max(len(TEACHING_LEVELS) - 1, 1)
    best = 0.0
    for a in a_levels:
        if a not in TEACHING_LEVELS:
            continue
        for b in b_levels:
            if b not in TEACHING_LEVELS:
                continue
            distance = abs(TEACHING_LEVELS.index(a) - TEACHING_LEVELS.index(b))
            best = max(best, 1.0 - distance / span)
    return best


def class_size_similarity(a: int | None, b: int | None) -> float:
    """1 - |a - b| / max(a, b), clamped to [0, 1]."""
    if not a or not b or a <= 0 or b <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - abs(a - b) / max(a, b)))


def social_similarity(*, shared_neighbors: int, is_friend_of_friend: bool) -> float:
    """Collaborative signal from the accepted-connection graph."""
    if shared_neighbors <= 0 and not is_friend_of_friend:
        return 0.0
    shared_score = 1.0 - math.exp(-0.55 * max(shared_neighbors, 0))
    fof_score = 0.45 if is_friend_of_friend else 0.0
    return max(0.0, min(1.0, max(shared_score, fof_score)))


def quality_similarity(
    average_rating: float | None,
    rating_count: int | None,
    *,
    prior: float | None = None,
    prior_strength: float | None = None,
) -> float:
    """Bayesian average of 1–5 ratings, mapped to [0, 1]."""
    prior = settings.rec_quality_prior if prior is None else prior
    m = settings.rec_quality_prior_strength if prior_strength is None else prior_strength
    count = max(0, int(rating_count or 0))
    avg = float(average_rating or 0.0)
    bayesian = (
        prior
        if count <= 0 or avg <= 0
        else (m * prior + count * avg) / (m + count)
    )
    return max(0.0, min(1.0, (bayesian - 1.0) / 4.0))


@dataclass
class ScoreBreakdown:
    total: float
    components: dict[str, float]
    weights: dict[str, float]
    distance_km: float | None = None
    shared_terms: list[str] = field(default_factory=list)
    shared_education_levels: list[str] = field(default_factory=list)
    shared_teaching_methods: list[str] = field(default_factory=list)
    shared_neighbors: int = 0

    @property
    def contributions(self) -> dict[str, float]:
        return {k: self.components[k] * self.weights[k] for k in self.components}


def score_profiles(
    viewer: TeacherProfile,
    candidate: TeacherProfile,
    weights: dict[str, float] | None = None,
    education_overrides: dict[str, dict[str, float]] | None = None,
    *,
    social_score: float = 0.0,
    shared_neighbors: int = 0,
) -> ScoreBreakdown:
    """Score one candidate against the viewer. Pure function - easy to test."""
    weights = normalise_recommendation_weights(weights or settings.recommendation_weights)
    overrides = (
        education_overrides
        if education_overrides is not None
        else settings.education_compatibility_overrides
    )

    viewer_terms = list(viewer.subjects or []) + list(viewer.fields_of_expertise or [])
    candidate_terms = list(candidate.subjects or []) + list(candidate.fields_of_expertise or [])

    location_score, distance_km = location_similarity(
        viewer.latitude, viewer.longitude, candidate.latitude, candidate.longitude
    )

    components = {
        "semantic": semantic_similarity(
            viewer.teaching_style_embedding, candidate.teaching_style_embedding
        ),
        "expertise": expertise_similarity(viewer_terms, candidate_terms),
        "education": education_similarity(
            viewer.education_levels, candidate.education_levels, overrides
        ),
        "teaching_level": teaching_level_similarity(
            viewer.teaching_levels, candidate.teaching_levels
        ),
        "location": location_score,
        "class_size": class_size_similarity(viewer.class_size, candidate.class_size),
        "social": max(0.0, min(1.0, social_score)),
        "quality": quality_similarity(candidate.average_rating, candidate.rating_count),
    }
    total = sum(components[key] * weights[key] for key in components)

    shared_terms = sorted(canonical_terms(viewer_terms) & canonical_terms(candidate_terms))
    shared_levels = [
        lvl for lvl in (viewer.education_levels or []) if lvl in (candidate.education_levels or [])
    ]
    shared_methods = [
        m for m in (viewer.teaching_methods or []) if m in (candidate.teaching_methods or [])
    ]

    return ScoreBreakdown(
        total=max(0.0, min(1.0, total)),
        components=components,
        weights=weights,
        distance_km=distance_km,
        shared_terms=shared_terms,
        shared_education_levels=shared_levels,
        shared_teaching_methods=shared_methods,
        shared_neighbors=shared_neighbors,
    )


def build_reasons(
    breakdown: ScoreBreakdown,
    viewer: TeacherProfile,
    candidate: TeacherProfile,
    max_reasons: int = 5,
) -> tuple[list[str], list[dict]]:
    """Turn component scores into display strings, strongest contribution first."""
    entries: list[tuple[float, str, str, float]] = []
    contributions = breakdown.contributions
    components = breakdown.components

    semantic = components["semantic"]
    if semantic >= 0.35:
        label = f"{round(semantic * 100)}% similarity in teaching philosophy"
        if breakdown.shared_teaching_methods:
            methods = ", ".join(humanize(m) for m in breakdown.shared_teaching_methods[:2])
            label = f"{label} ({methods})"
        entries.append((contributions["semantic"], "semantic", label, semantic))

    if breakdown.shared_terms:
        shown = ", ".join(humanize(t) for t in breakdown.shared_terms[:3])
        extra = len(breakdown.shared_terms) - 3
        label = f"Shared expertise: {shown}" + (f" +{extra} more" if extra > 0 else "")
        entries.append((contributions["expertise"], "expertise", label, components["expertise"]))
    elif components["expertise"] >= 0.25:
        entries.append(
            (
                contributions["expertise"],
                "expertise",
                "Closely related subject areas",
                components["expertise"],
            )
        )

    if breakdown.shared_education_levels:
        label = "Same education level: " + ", ".join(
            humanize(lvl) for lvl in breakdown.shared_education_levels[:2]
        )
        entries.append((contributions["education"], "education", label, components["education"]))
    elif components["education"] >= 0.4 and candidate.education_levels:
        label = "Compatible education levels: " + ", ".join(
            humanize(lvl) for lvl in candidate.education_levels[:2]
        )
        entries.append((contributions["education"], "education", label, components["education"]))

    if components["teaching_level"] >= 0.5 and candidate.teaching_levels:
        shared = [lvl for lvl in (viewer.teaching_levels or []) if lvl in candidate.teaching_levels]
        if shared:
            label = "Both teach " + " and ".join(humanize(lvl) for lvl in shared[:2]) + " learners"
        else:
            label = "Adjacent learner levels: " + ", ".join(
                humanize(lvl) for lvl in candidate.teaching_levels[:2]
            )
        entries.append(
            (contributions["teaching_level"], "teaching_level", label, components["teaching_level"])
        )

    if breakdown.distance_km is not None and components["location"] > 0:
        distance = breakdown.distance_km
        if distance < 1:
            label = "Based in the same neighbourhood"
        elif candidate.location_name and distance < 25:
            label = f"{round(distance)} km away in {candidate.location_name}"
        else:
            label = f"Located {round(distance)} km away"
        entries.append((contributions["location"], "location", label, components["location"]))

    if components["class_size"] >= 0.7 and viewer.class_size and candidate.class_size:
        label = f"Similar class size: {viewer.class_size} vs {candidate.class_size}"
        entries.append((contributions["class_size"], "class_size", label, components["class_size"]))

    if components.get("social", 0) >= 0.35:
        if breakdown.shared_neighbors > 0:
            n = breakdown.shared_neighbors
            label = f"{n} shared colleague{'s' if n != 1 else ''} in your network"
        else:
            label = "Connected through colleagues you already know"
        entries.append((contributions["social"], "social", label, components["social"]))

    if components.get("quality", 0) >= 0.55 and (candidate.rating_count or 0) > 0:
        label = (
            f"Strong peer rating ({candidate.average_rating:.1f}/5, "
            f"n={candidate.rating_count})"
        )
        entries.append((contributions["quality"], "quality", label, components["quality"]))

    entries.sort(key=lambda item: item[0], reverse=True)
    top = entries[:max_reasons]

    reasons = [label for _, _, label, _ in top]
    explanation = [
        {
            "factor": factor,
            "label": label,
            "score": round(score, 4),
            "weight": round(breakdown.weights[factor], 4),
            "contribution": round(contribution, 4),
        }
        for contribution, factor, label, score in top
    ]
    return reasons, explanation


def _embedding_sim(a: TeacherProfile, b: TeacherProfile) -> float:
    if a.teaching_style_embedding is not None and b.teaching_style_embedding is not None:
        return max(
            0.0,
            cosine_similarity(list(a.teaching_style_embedding), list(b.teaching_style_embedding)),
        )
    a_terms = canonical_terms(list(a.subjects or []) + list(a.fields_of_expertise or []))
    b_terms = canonical_terms(list(b.subjects or []) + list(b.fields_of_expertise or []))
    if not a_terms or not b_terms:
        return 0.0
    return len(a_terms & b_terms) / len(a_terms | b_terms)


def mmr_rerank(
    items: list[RecommendationItem],
    *,
    lambda_: float | None = None,
    limit: int,
) -> list[RecommendationItem]:
    """Maximal Marginal Relevance over teaching-style / subject similarity."""
    if not items:
        return []
    lambda_ = settings.rec_mmr_lambda if lambda_ is None else lambda_
    selected: list[RecommendationItem] = []
    remaining = list(items)
    while remaining and len(selected) < limit:
        best_idx = 0
        best_val = -1e9
        for idx, cand in enumerate(remaining):
            relevance = cand.breakdown.total
            diversity_pen = 0.0
            if selected:
                diversity_pen = max(
                    _embedding_sim(cand.profile, other.profile) for other in selected
                )
            value = lambda_ * relevance - (1 - lambda_) * diversity_pen
            if value > best_val:
                best_val = value
                best_idx = idx
        selected.append(remaining.pop(best_idx))
    return selected


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
@dataclass
class RecommendationItem:
    profile: TeacherProfile
    user: User
    breakdown: ScoreBreakdown
    reasons: list[str]
    explanation: list[dict]


@dataclass
class RecommendationResult:
    items: list[RecommendationItem]
    candidate_pool_size: int
    took_ms: float
    weights: dict[str, float]
    bandit_arm_id: str | None = None
    weight_source: str = "default"


class RecommendationService:
    """Candidate retrieval (pgvector ANN + structured overlap) then re-ranking."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _load_profile(self, user_id: uuid.UUID) -> TeacherProfile | None:
        return await self.db.scalar(
            select(TeacherProfile).where(TeacherProfile.user_id == user_id)
        )

    def _exclusion_clause(self, user_id: uuid.UUID, exclude_connected: bool = True):
        """Hide anyone already in your connection graph from Matches.

        Always excludes pending invitations (sent or received), accepted
        connections, blocks, and rejections. ``exclude_connected`` is retained
        for API compatibility and has no effect.
        """
        del exclude_connected  # API compat; pending/accepted are always hidden
        excluded = [
            ConnectionStatus.BLOCKED,
            ConnectionStatus.REJECTED,
            ConnectionStatus.PENDING,
            ConnectionStatus.ACCEPTED,
        ]
        return ~exists(
            select(Connection.id).where(
                and_(
                    Connection.status.in_(excluded),
                    or_(
                        and_(
                            Connection.requester_id == user_id,
                            Connection.receiver_id == TeacherProfile.user_id,
                        ),
                        and_(
                            Connection.receiver_id == user_id,
                            Connection.requester_id == TeacherProfile.user_id,
                        ),
                    ),
                )
            )
        )

    async def _fetch_candidates(
        self, viewer: TeacherProfile, pool_size: int, exclude_connected: bool
    ) -> list[tuple[TeacherProfile, User]]:
        base_filters = [
            TeacherProfile.user_id != viewer.user_id,
            User.is_active.is_(True),
            self._exclusion_clause(viewer.user_id, exclude_connected),
        ]

        candidates: dict[uuid.UUID, tuple[TeacherProfile, User]] = {}

        if viewer.teaching_style_embedding is not None:
            await self.db.execute(text(f"SET LOCAL hnsw.ef_search = {max(pool_size, 64)}"))
            ann_stmt = (
                select(TeacherProfile, User)
                .join(User, User.id == TeacherProfile.user_id)
                .where(*base_filters, TeacherProfile.teaching_style_embedding.is_not(None))
                .order_by(
                    TeacherProfile.teaching_style_embedding.cosine_distance(
                        viewer.teaching_style_embedding
                    )
                )
                .limit(pool_size)
            )
            for profile, user in (await self.db.execute(ann_stmt)).all():
                candidates[profile.user_id] = (profile, user)

        viewer_terms = list(viewer.subjects or []) + list(viewer.fields_of_expertise or [])
        if viewer_terms:
            overlap_stmt = (
                select(TeacherProfile, User)
                .join(User, User.id == TeacherProfile.user_id)
                .where(
                    *base_filters,
                    or_(
                        TeacherProfile.subjects.overlap(viewer_terms),
                        TeacherProfile.fields_of_expertise.overlap(viewer_terms),
                    ),
                )
                .order_by(
                    TeacherProfile.average_rating.desc(), TeacherProfile.rating_count.desc()
                )
                .limit(max(pool_size // 2, 50))
            )
            for profile, user in (await self.db.execute(overlap_stmt)).all():
                candidates.setdefault(profile.user_id, (profile, user))

        if not candidates:
            fallback_stmt = (
                select(TeacherProfile, User)
                .join(User, User.id == TeacherProfile.user_id)
                .where(*base_filters)
                .order_by(TeacherProfile.average_rating.desc(), TeacherProfile.rating_count.desc())
                .limit(pool_size)
            )
            for profile, user in (await self.db.execute(fallback_stmt)).all():
                candidates[profile.user_id] = (profile, user)

        return list(candidates.values())

    async def _social_scores(
        self, viewer_id: uuid.UUID, candidate_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[float, int]]:
        """Return candidate_id -> (social_score, shared_neighbor_count).

        Only loads the viewer's 1-hop and 2-hop neighbourhood — never the full
        connections table (that was O(all edges) per request).
        """
        if not candidate_ids:
            return {}

        # 1-hop: people the viewer is connected to.
        direct = (
            await self.db.execute(
                select(Connection.requester_id, Connection.receiver_id).where(
                    Connection.status == ConnectionStatus.ACCEPTED,
                    or_(
                        Connection.requester_id == viewer_id,
                        Connection.receiver_id == viewer_id,
                    ),
                )
            )
        ).all()
        viewer_friends: set[uuid.UUID] = set()
        for a, b in direct:
            viewer_friends.add(b if a == viewer_id else a)

        if not viewer_friends:
            return dict.fromkeys(candidate_ids, (0.0, 0))

        # 2-hop: only friend↔candidate edges (enough for FoF + shared-neighbor counts).
        friend_list = list(viewer_friends)[:200]
        candidate_set = set(candidate_ids)
        if not friend_list or not candidate_set:
            return dict.fromkeys(candidate_ids, (0.0, 0))

        hop2 = (
            await self.db.execute(
                select(Connection.requester_id, Connection.receiver_id).where(
                    Connection.status == ConnectionStatus.ACCEPTED,
                    or_(
                        and_(
                            Connection.requester_id.in_(friend_list),
                            Connection.receiver_id.in_(candidate_ids),
                        ),
                        and_(
                            Connection.receiver_id.in_(friend_list),
                            Connection.requester_id.in_(candidate_ids),
                        ),
                    ),
                )
            )
        ).all()

        shared_counts: dict[uuid.UUID, int] = defaultdict(int)
        fof: set[uuid.UUID] = set()
        for a, b in hop2:
            if a in viewer_friends and b in candidate_set:
                shared_counts[b] += 1
                fof.add(b)
            elif b in viewer_friends and a in candidate_set:
                shared_counts[a] += 1
                fof.add(a)

        out: dict[uuid.UUID, tuple[float, int]] = {}
        for cid in candidate_ids:
            shared = shared_counts.get(cid, 0)
            out[cid] = (
                social_similarity(shared_neighbors=shared, is_friend_of_friend=cid in fof),
                shared,
            )
        return out

    async def recommend(
        self,
        user_id: uuid.UUID,
        limit: int | None = None,
        *,
        exclude_connected: bool = False,
        pool_size: int | None = None,
        log_events: bool = True,
        mmr: bool | None = None,
    ) -> RecommendationResult:
        started = time.perf_counter()
        limit = limit or settings.rec_default_limit
        # Cap the scored pool relative to the page size unless the caller
        # explicitly overrode ``pool_size`` (via the API query param).
        if pool_size is None:
            pool_size = min(settings.rec_candidate_pool, max(limit * 8, 64))
        use_mmr = settings.rec_mmr_enabled if mmr is None else mmr

        viewer = await self._load_profile(user_id)
        if viewer is None:
            raise ProfileRequiredError(
                "Create your teacher profile first - recommendations are based on it."
            )

        await ensure_cooccurrence(self.db, blocking=False)

        selected = await bandit_service.resolve_weights(
            self.db, profile_weights=viewer.recommendation_weights
        )
        weights = selected.weights
        overrides = settings.education_compatibility_overrides
        candidates = await self._fetch_candidates(viewer, pool_size, exclude_connected)
        social_map = await self._social_scores(
            viewer.user_id, [profile.user_id for profile, _ in candidates]
        )

        scored: list[RecommendationItem] = []
        for profile, user in candidates:
            social_score, shared_n = social_map.get(profile.user_id, (0.0, 0))
            breakdown = score_profiles(
                viewer,
                profile,
                weights,
                overrides,
                social_score=social_score,
                shared_neighbors=shared_n,
            )
            reasons, explanation = build_reasons(breakdown, viewer, profile)
            scored.append(
                RecommendationItem(
                    profile=profile,
                    user=user,
                    breakdown=breakdown,
                    reasons=reasons,
                    explanation=explanation,
                )
            )

        scored.sort(
            key=lambda item: (item.breakdown.total, item.profile.average_rating), reverse=True
        )
        if use_mmr:
            # Diversify only among the strongest candidates — full-pool MMR is O(n²).
            mmr_input = scored[: max(limit * 5, 40)]
            top = mmr_rerank(mmr_input, limit=limit)
        else:
            top = scored[:limit]

        if log_events and top:
            await self._log_events(user_id, top, arm_id=selected.arm_id)

        took_ms = (time.perf_counter() - started) * 1000
        logger.debug(
            "recommendations user=%s pool=%d returned=%d arm=%s source=%s in %.1fms",
            user_id,
            len(candidates),
            len(top),
            selected.arm_id,
            selected.source,
            took_ms,
        )
        return RecommendationResult(
            items=top,
            candidate_pool_size=len(candidates),
            took_ms=round(took_ms, 2),
            weights=weights,
            bandit_arm_id=selected.arm_id,
            weight_source=selected.source,
        )

    async def _log_events(
        self,
        user_id: uuid.UUID,
        items: list[RecommendationItem],
        *,
        arm_id: str | None,
    ) -> None:
        """Record what we served (upsert) for bandit learning. Best effort."""
        rows = [
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "recommended_user_id": item.profile.user_id,
                "match_score": item.breakdown.total,
                "components": {k: round(v, 4) for k, v in item.breakdown.components.items()},
                "reasons": item.reasons,
                "bandit_arm_id": arm_id,
                "rank_position": index + 1,
            }
            for index, item in enumerate(items)
        ]
        try:
            stmt = pg_insert(RecommendationEvent).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_recommendation_pair",
                set_={
                    "match_score": stmt.excluded.match_score,
                    "components": stmt.excluded.components,
                    "reasons": stmt.excluded.reasons,
                    "bandit_arm_id": stmt.excluded.bandit_arm_id,
                    "rank_position": stmt.excluded.rank_position,
                    "updated_at": func.now(),
                },
            )
            await self.db.execute(stmt)
            await self.db.commit()
        except Exception:  # pragma: no cover - telemetry must never break the response
            logger.exception("Failed to log recommendation events")
            await self.db.rollback()

    # --- resource recommendations ------------------------------------------ #
    async def recommend_resources(
        self, user_id: uuid.UUID, limit: int = 10
    ) -> list[tuple[Resource, float, list[str]]]:
        """Resources that fit the viewer's subjects, level and teaching style."""
        viewer = await self._load_profile(user_id)
        if viewer is None:
            raise ProfileRequiredError(
                "Create your teacher profile first - resource recommendations are based on it."
            )

        pool = max(limit * 10, 100)
        stmt = select(Resource).where(Resource.owner_id != user_id).limit(pool)
        if viewer.teaching_style_embedding is not None:
            stmt = stmt.where(Resource.embedding.is_not(None)).order_by(
                Resource.embedding.cosine_distance(viewer.teaching_style_embedding)
            )
        else:
            subjects = list(viewer.subjects or [])
            if subjects:
                stmt = stmt.where(Resource.subject.in_(subjects))
            stmt = stmt.order_by(Resource.created_at.desc())

        resources = list((await self.db.scalars(stmt)).all())

        viewer_subjects = canonical_terms(
            list(viewer.subjects or []) + list(viewer.fields_of_expertise or [])
        )
        results: list[tuple[Resource, float, list[str]]] = []
        for resource in resources:
            semantic = semantic_similarity(viewer.teaching_style_embedding, resource.embedding)
            subject_score = 0.0
            reasons: list[str] = []
            if resource.subject and resource.subject in viewer_subjects:
                subject_score = 1.0
                reasons.append(f"Matches your subject: {humanize(resource.subject)}")
            elif resource.subject:
                subject_score = max(
                    (combined_relatedness(resource.subject, term) for term in viewer_subjects),
                    default=0.0,
                )
                if subject_score >= 0.6:
                    reasons.append(f"Related subject: {humanize(resource.subject)}")

            level_score = (
                1.0
                if resource.education_level
                and resource.education_level in (viewer.education_levels or [])
                else 0.0
            )
            if level_score:
                reasons.append(f"Built for {humanize(resource.education_level)}")

            method_score = (
                1.0
                if resource.teaching_method
                and resource.teaching_method in (viewer.teaching_methods or [])
                else 0.0
            )
            if method_score:
                reasons.append(f"Uses your style: {humanize(resource.teaching_method)}")

            if semantic >= 0.35:
                reasons.append(f"{round(semantic * 100)}% match to your teaching profile")

            score = 0.4 * semantic + 0.3 * subject_score + 0.2 * level_score + 0.1 * method_score
            results.append((resource, max(0.0, min(1.0, score)), reasons[:4]))

        results.sort(key=lambda row: row[1], reverse=True)
        return results[:limit]
