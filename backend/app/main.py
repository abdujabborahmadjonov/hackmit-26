"""EduMatch API entrypoint."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    ai,
    auth,
    class_profiles,
    connections,
    forum,
    messages,
    profiles,
    ratings,
    recommendations,
    resources,
    search,
    student_tokens,
    technique_search,
    techniques,
    users,
)
from app.config import orphaned_env_lines, settings
from app.database import engine, ensure_extensions
from app.services.embedding_service import get_embedding_service

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("edumatch")

DESCRIPTION = """
**EduMatch** is an AI-powered professional network for educators.

Teachers describe *what* and *how* they teach; EduMatch combines structured
attributes with semantic embeddings of their teaching style to recommend the
colleagues they are most likely to collaborate well with.

### Where to start
1. `POST /auth/register` then `POST /auth/login` for a JWT.
2. `POST /profiles` to describe your teaching.
3. `GET /recommendations` for your matches - each one explains *why*.
4. `GET /search/teachers` for filtered/semantic/geographic discovery.

### How matching works
`score = 0.30*semantic + 0.20*expertise + 0.15*education + 0.15*teaching_level
+ 0.10*location + 0.10*class_size`, all components normalised to 0-1 and the
weights configurable via `REC_WEIGHT_*` environment variables.

### Privacy
Only approximate (city-level) locations are stored, rounded to ~1 km.
Messages are encrypted in transit via HTTPS and stored server-side - EduMatch
does **not** provide end-to-end encryption.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Registration, login and the current account."},
    {"name": "users", "description": "Account records."},
    {"name": "profiles", "description": "Teacher profiles - the input to all matching."},
    {"name": "recommendations", "description": "The hybrid matching engine and its explanations."},
    {"name": "search", "description": "Filtered, semantic and geographic discovery."},
    {"name": "resources", "description": "Teaching materials: metadata, uploads, recommendations."},
    {"name": "ratings", "description": "Peer and verified student ratings."},
    {
        "name": "student-tokens",
        "description": "Classroom codes educators issue so students can leave verified ratings.",
    },
    {"name": "connections", "description": "Connection requests between educators."},
    {"name": "messages", "description": "Direct messaging (HTTPS transport security only)."},
    {"name": "forum", "description": "Public discussion topics and replies between educators."},
    {"name": "class-profiles", "description": "Per-class teaching context for technique search."},
    {"name": "techniques", "description": "Teaching technique cards, drafts, and student ratings."},
    {
        "name": "technique-search",
        "description": "Concept/problem search, follow-ups, ranking, and planning mode.",
    },
    {"name": "ai", "description": "Generative features: collaboration briefs and syllabus import."},
    {"name": "system", "description": "Health and diagnostics."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)

    orphans = orphaned_env_lines()
    if orphans:
        logger.warning(
            "%s line(s) in .env hold a value with no NAME= in front of them (line %s). "
            "Those settings are being ignored - check for a key pasted without its "
            "variable name.",
            len(orphans),
            ", ".join(str(n) for n in orphans),
        )
    try:
        await ensure_extensions()
    except Exception as exc:  # pragma: no cover - surfaced at /health instead
        logger.error("Could not prepare database extensions: %s", exc)

    service = get_embedding_service()
    logger.info("Embeddings: provider=%s dim=%s", service.provider_name, service.dim)

    if settings.search_provider == "elasticsearch":
        from app.services import elasticsearch_service as es

        try:
            await es.ensure_indices()
            logger.info("Elasticsearch engine ready at %s", settings.elasticsearch_url)
        except Exception as exc:
            logger.warning(
                "Elasticsearch not reachable (%s). %s",
                exc,
                "Falling back to Postgres search."
                if settings.search_fallback_to_postgres
                else "Search requests will fail.",
            )
    yield

    if settings.search_provider == "elasticsearch":
        from app.services import elasticsearch_service as es

        await es.close_client()

    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        openapi_tags=TAGS_METADATA,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        contact={"name": "EduMatch (HackMIT 2026)"},
        license_info={"name": "MIT"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """Readable validation errors instead of raw pydantic dumps."""
        problems = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or error["loc"][0],
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": "Validation failed", "errors": problems},
        )

    for router in (
        auth.router,
        ai.router,
        users.router,
        profiles.router,
        recommendations.router,
        search.router,
        resources.router,
        ratings.router,
        student_tokens.router,
        connections.router,
        messages.router,
        forum.router,
        class_profiles.router,
        techniques.router,
        technique_search.router,
    ):
        app.include_router(router)

    # Serve locally stored uploads (the S3 backend returns absolute URLs instead).
    if settings.storage_provider == "local":
        uploads = Path(settings.storage_local_dir).resolve() / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        app.mount("/static/uploads", StaticFiles(directory=str(uploads)), name="uploads")

    @app.get("/", tags=["system"], summary="Service banner")
    async def root() -> dict:
        return {
            "service": settings.app_name,
            "version": "1.0.0",
            "docs": "/docs",
            "search_engine": settings.search_provider,
            "embedding_provider": settings.embedding_provider,
        }

    @app.get("/health", tags=["system"], summary="Liveness and dependency health")
    async def health() -> JSONResponse:
        from sqlalchemy import text

        payload: dict = {"status": "ok", "database": "ok"}
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            payload["status"] = "degraded"
            payload["database"] = f"error: {exc}"

        if settings.search_provider == "elasticsearch":
            from app.services import elasticsearch_service as es

            payload["elasticsearch"] = "ok" if await es.ping() else "unreachable"
            if payload["elasticsearch"] != "ok" and not settings.search_fallback_to_postgres:
                payload["status"] = "degraded"

        code = status.HTTP_200_OK if payload["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=code, content=payload)

    return app


app = create_app()
