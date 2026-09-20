"""Expertise relatedness: hand-curated pairs plus corpus co-occurrence.

`combined_relatedness` returns max(hand, co-occurrence). Co-occurrence is
refreshed from teacher profile subject/expertise bags and cached in memory.
"""

from __future__ import annotations

import logging
import math
import time
from collections import Counter
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import TeacherProfile
from app.taxonomy import canonical_terms, term_relatedness

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str], float] = {}
_CACHE_BUILT_AT: float = 0.0
_CACHE_TTL_SECONDS = 300.0
_REFRESH_IN_FLIGHT = False
# Cap profiles scanned so a cold rebuild cannot stall a request for seconds.
_MAX_PROFILES_SCANNED = 2_500


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def cooccurrence_relatedness(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return _CACHE.get(_pair_key(a, b), 0.0)


def combined_relatedness(a: str, b: str) -> float:
    """Hand graph + co-occurrence; used by soft Jaccard expertise matching."""
    if a == b:
        return 1.0
    return max(term_relatedness(a, b), cooccurrence_relatedness(a, b))


def cache_age_seconds() -> float:
    if _CACHE_BUILT_AT <= 0:
        return float("inf")
    return time.monotonic() - _CACHE_BUILT_AT


def clear_cooccurrence_cache() -> None:
    global _CACHE, _CACHE_BUILT_AT
    _CACHE = {}
    _CACHE_BUILT_AT = 0.0


async def refresh_cooccurrence(db: AsyncSession, *, force: bool = False) -> int:
    """Rebuild the co-occurrence relatedness cache from profile term bags."""
    global _CACHE, _CACHE_BUILT_AT, _REFRESH_IN_FLIGHT
    if not force and cache_age_seconds() < _CACHE_TTL_SECONDS and _CACHE:
        return len(_CACHE)
    if _REFRESH_IN_FLIGHT and not force:
        return len(_CACHE)

    _REFRESH_IN_FLIGHT = True
    try:
        rows = (
            await db.execute(
                select(TeacherProfile.subjects, TeacherProfile.fields_of_expertise).limit(
                    _MAX_PROFILES_SCANNED
                )
            )
        ).all()

        term_counts: Counter[str] = Counter()
        pair_counts: Counter[tuple[str, str]] = Counter()
        docs = 0
        for subjects, expertise in rows:
            terms = sorted(canonical_terms(list(subjects or []) + list(expertise or [])))
            if len(terms) < 2:
                if terms:
                    term_counts.update(terms)
                    docs += 1
                continue
            term_counts.update(terms)
            docs += 1
            for a, b in combinations(terms, 2):
                pair_counts[_pair_key(a, b)] += 1

        if docs == 0:
            _CACHE = {}
            _CACHE_BUILT_AT = time.monotonic()
            return 0

        new_cache: dict[tuple[str, str], float] = {}
        for (a, b), joint in pair_counts.items():
            if joint < 2:
                continue
            pa = term_counts[a] / docs
            pb = term_counts[b] / docs
            pab = joint / docs
            if pa <= 0 or pb <= 0 or pab <= 0:
                continue
            pmi = math.log(pab / (pa * pb))
            score = max(0.0, min(0.95, pmi / 3.0))
            if score >= 0.25:
                new_cache[(a, b)] = score

        _CACHE = new_cache
        _CACHE_BUILT_AT = time.monotonic()
        logger.info(
            "Refreshed expertise co-occurrence cache (%d pairs from %d profiles)",
            len(_CACHE),
            docs,
        )
        return len(_CACHE)
    finally:
        _REFRESH_IN_FLIGHT = False


async def ensure_cooccurrence(db: AsyncSession, *, blocking: bool = True) -> None:
    """Refresh relatedness cache.

    On the recommendation hot path pass ``blocking=False`` so a cold cache
    uses hand-curated relatedness only for this request (refresh is skipped
    rather than scanning thousands of profiles inline).
    """
    try:
        if not blocking and not _CACHE:
            # Mark empty so we do not stampede; a later blocking caller / demo
            # script can fill it. Hand-curated RELATED_TERMS still apply.
            return
        await refresh_cooccurrence(db)
    except Exception:  # pragma: no cover
        logger.exception("Failed to refresh co-occurrence relatedness")
