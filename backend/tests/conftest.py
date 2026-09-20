"""Shared pytest fixtures.

Unit tests (scoring, embeddings, geo) run anywhere. API tests need PostgreSQL
with pgvector; if it is not reachable they are skipped with an explanatory
message rather than failing the suite.

    TEST_DATABASE_URL=postgresql+asyncpg://edumatch:edumatch@localhost:5432/edumatch_test
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models as _models  # noqa: F401  (registers the tables)
from app.config import settings
from app.database import Base, create_engine, get_db
from app.main import app as fastapi_app
from app.utils.rate_limit import reset_rate_limits


def _test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = settings.database_url
    base, _, database = url.rpartition("/")
    if database.endswith("_test"):
        return url
    return f"{base}/{database}_test"


TEST_DATABASE_URL = _test_database_url()


async def _prepare_database() -> str | None:
    """Create the extensions and a clean schema. Returns a reason on failure."""
    engine = create_engine(TEST_DATABASE_URL, pool_size=1, max_overflow=0)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()


# Done once, at collection time, in its own event loop. Every fixture below is
# function-scoped so that asyncpg connections never cross event loops.
_SKIP_REASON = asyncio.run(_prepare_database())

requires_db = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=(
        f"PostgreSQL+pgvector not available at {TEST_DATABASE_URL.split('@')[-1]} "
        f"({_SKIP_REASON}). Start it with: docker compose up -d postgres"
    ),
)

_TRUNCATE_SQL = None


def _truncate_sql() -> str:
    global _TRUNCATE_SQL
    if _TRUNCATE_SQL is None:
        tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
        _TRUNCATE_SQL = f"TRUNCATE {tables} RESTART IDENTITY CASCADE"
    return _TRUNCATE_SQL


@pytest_asyncio.fixture
async def engine():
    engine = create_engine(TEST_DATABASE_URL, pool_size=5, max_overflow=5)
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(_truncate_sql()))
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine) -> AsyncGenerator[AsyncClient, None]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    reset_rate_limits()
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def default_search_provider(monkeypatch):
    """Pin the search engine for every test.

    Otherwise the suite inherits whatever SEARCH_PROVIDER the developer has in
    .env: point it at a live Elasticsearch and the search tests start reading
    that index - real data, not the fixtures they just created. Tests that want
    the Elasticsearch backend opt in by monkeypatching it themselves.
    """
    monkeypatch.setattr(settings, "search_provider", "postgres")


@pytest.fixture(autouse=True)
def deterministic_recommendations(monkeypatch):
    """Disable the bandit so ranking assertions stay stable across CI runs.

    Thompson sampling is covered by ``test_bandit.py``. MMR stays on so its
    integration paths remain covered; tests that need pure score order pass
    ``?mmr=false`` explicitly.
    """
    monkeypatch.setattr(settings, "rec_bandit_enabled", False)


# --------------------------------------------------------------------------- #
# Convenience helpers
# --------------------------------------------------------------------------- #
DEFAULT_PASSWORD = "TestPassword123"


async def register(
    client: AsyncClient,
    email: str | None = None,
    first_name: str = "Test",
    last_name: str = "Teacher",
    password: str = DEFAULT_PASSWORD,
) -> dict:
    """Register an account and return {email, password, token, headers}."""
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {
        "email": email,
        "password": password,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


async def create_profile(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "bio": "I teach computer science using project-based learning.",
        "location_name": "Boston, Massachusetts",
        "latitude": 42.36,
        "longitude": -71.06,
        "education_levels": ["high_school"],
        "subjects": ["computer_science", "python"],
        "fields_of_expertise": ["software_engineering"],
        "teaching_levels": ["beginner", "intermediate"],
        "teaching_methods": ["project_based", "collaborative"],
        "teaching_style": "Project-based, collaborative and hands-on.",
        "class_size": 25,
        "years_experience": 5,
        "languages": ["English"],
    }
    payload.update(overrides)
    response = await client.post("/profiles", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def register_with_profile(client: AsyncClient, first_name: str = "Test", **profile) -> dict:
    account = await register(client, first_name=first_name)
    account["profile"] = await create_profile(client, account["headers"], **profile)
    account["user_id"] = account["profile"]["user_id"]
    return account


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
