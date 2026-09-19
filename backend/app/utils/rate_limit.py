"""A small in-process sliding-window rate limiter.

Good enough for a hackathon demo and for blunting credential stuffing on the
auth routes. For multi-worker production you would back this with Redis - the
dependency signature stays the same.
"""

# NOTE: no `from __future__ import annotations` here on purpose - FastAPI
# cannot resolve string annotations on a class-based dependency's __call__,
# which would make `request: Request` look like a required body field.

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.config import settings

_WINDOW_SECONDS = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request, bucket: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    return f"{bucket}:{ip}"


def reset_rate_limits() -> None:
    """Test helper."""
    _hits.clear()


class RateLimiter:
    """Dependency factory: `Depends(RateLimiter("auth", 20))`."""

    def __init__(self, bucket: str, limit_per_minute: int | None = None) -> None:
        self.bucket = bucket
        self.limit = limit_per_minute or settings.rate_limit_per_minute

    async def __call__(self, request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        key = _client_key(request, self.bucket)
        now = time.monotonic()
        window = _hits[key]
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self.limit:
            retry_after = int(_WINDOW_SECONDS - (now - window[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


default_rate_limit = RateLimiter("default")
auth_rate_limit = RateLimiter("auth", settings.auth_rate_limit_per_minute)

AuthRateLimit = Annotated[None, Depends(auth_rate_limit)]
DefaultRateLimit = Annotated[None, Depends(default_rate_limit)]
