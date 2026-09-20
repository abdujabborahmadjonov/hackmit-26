"""Unit tests for expertise relatedness (hand graph + co-occurrence cache)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import relatedness_service as rel
from app.services.relatedness_service import (
    cache_age_seconds,
    clear_cooccurrence_cache,
    combined_relatedness,
    cooccurrence_relatedness,
    ensure_cooccurrence,
    refresh_cooccurrence,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cooccurrence_cache()
    rel._REFRESH_IN_FLIGHT = False
    yield
    clear_cooccurrence_cache()
    rel._REFRESH_IN_FLIGHT = False


def test_identical_terms_are_fully_related():
    assert cooccurrence_relatedness("python", "python") == 1.0
    assert combined_relatedness("python", "python") == 1.0


def test_empty_cache_falls_back_to_hand_graph():
    assert cooccurrence_relatedness("python", "java") == 0.0
    assert combined_relatedness("history", "social_studies") >= 0.8


def test_cache_age_is_infinite_when_cold():
    assert cache_age_seconds() == float("inf")


def _mock_db(rows: list[tuple]) -> AsyncMock:
    result = MagicMock()
    result.all.return_value = rows
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _strong_cooccurrence_rows() -> list[tuple]:
    # Rare terms that always co-occur beat the PMI ≥ 0.25 gate; filler docs
    # keep the marginals low enough for a strong association score.
    rows = [([f"filler_{i}", f"noise_{i}"], []) for i in range(20)]
    rows.extend([(["rare_alpha", "rare_beta"], []) for _ in range(5)])
    rows.append((["lonely"], []))  # singleton still counts as a document
    return rows


@pytest.mark.asyncio
async def test_refresh_builds_pmi_pairs_from_profiles():
    n = await refresh_cooccurrence(_mock_db(_strong_cooccurrence_rows()), force=True)
    assert n >= 1
    assert cache_age_seconds() < float("inf")
    score = cooccurrence_relatedness("rare_alpha", "rare_beta")
    assert score >= 0.25
    assert combined_relatedness("rare_alpha", "rare_beta") >= score


@pytest.mark.asyncio
async def test_refresh_skips_when_cache_is_fresh():
    await refresh_cooccurrence(_mock_db(_strong_cooccurrence_rows()), force=True)
    first_size = len(rel._CACHE)
    assert first_size >= 1
    db = _mock_db([])
    n = await refresh_cooccurrence(db, force=False)
    assert n == first_size
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_with_no_profiles_clears_cache():
    rel._CACHE = {("x", "y"): 0.5}
    n = await refresh_cooccurrence(_mock_db([]), force=True)
    assert n == 0
    assert rel._CACHE == {}


@pytest.mark.asyncio
async def test_refresh_in_flight_returns_existing():
    rel._CACHE = {("a", "b"): 0.4}
    rel._CACHE_BUILT_AT = 1.0
    rel._REFRESH_IN_FLIGHT = True
    db = _mock_db([])
    assert await refresh_cooccurrence(db, force=False) == 1
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_nonblocking_skips_cold_cache():
    db = AsyncMock()
    await ensure_cooccurrence(db, blocking=False)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_blocking_refreshes():
    db = _mock_db(_strong_cooccurrence_rows())
    await ensure_cooccurrence(db, blocking=True)
    assert cache_age_seconds() < float("inf")
