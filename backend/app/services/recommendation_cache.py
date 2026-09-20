"""Short-lived in-process cache for Matches API responses."""

from __future__ import annotations

import time
import uuid

from app.config import settings
from app.schemas.recommendation import RecommendationResponse

_RESPONSE_CACHE: dict[str, tuple[float, RecommendationResponse]] = {}
_RESPONSE_CACHE_MAX = 256


def cache_key(
    user_id: uuid.UUID,
    *,
    limit: int,
    exclude_connected: bool,
    candidate_pool: int | None,
    mmr: bool | None,
) -> str:
    return f"{user_id}:{limit}:{exclude_connected}:{candidate_pool}:{mmr}"


def cache_get(key: str) -> RecommendationResponse | None:
    ttl = settings.rec_response_cache_ttl_seconds
    if ttl <= 0:
        return None
    hit = _RESPONSE_CACHE.get(key)
    if hit is None:
        return None
    stamped, payload = hit
    if time.monotonic() - stamped > ttl:
        _RESPONSE_CACHE.pop(key, None)
        return None
    return payload


def cache_put(key: str, payload: RecommendationResponse) -> None:
    ttl = settings.rec_response_cache_ttl_seconds
    if ttl <= 0:
        return
    _RESPONSE_CACHE[key] = (time.monotonic(), payload)
    if len(_RESPONSE_CACHE) > _RESPONSE_CACHE_MAX:
        oldest = sorted(_RESPONSE_CACHE.items(), key=lambda item: item[1][0])[
            : max(1, _RESPONSE_CACHE_MAX // 4)
        ]
        for stale_key, _ in oldest:
            _RESPONSE_CACHE.pop(stale_key, None)


def invalidate_recommendation_cache(user_id: uuid.UUID | None = None) -> None:
    """Drop cached Matches payloads (one viewer, or everyone)."""
    if user_id is None:
        _RESPONSE_CACHE.clear()
        return
    prefix = f"{user_id}:"
    for key in [k for k in _RESPONSE_CACHE if k.startswith(prefix)]:
        _RESPONSE_CACHE.pop(key, None)
