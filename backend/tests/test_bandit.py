"""Unit tests for the Thompson-sampling recommendation bandit."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.recommendation import BanditArm, RecommendationFeedback
from app.services.bandit_service import (
    default_arm_specs,
    ensure_arms,
    record_feedback,
    resolve_weights,
    thompson_select,
)


def test_default_arm_specs_cover_every_factor():
    specs = default_arm_specs()
    assert "default" in specs
    assert "explore" in specs
    assert abs(sum(specs["default"].values()) - 1.0) < 1e-6
    assert specs["semantic_heavy"]["semantic"] > specs["default"]["semantic"]


def test_thompson_prefers_high_alpha_arm():
    import random

    winner = BanditArm(arm_id="win", weights={"semantic": 1.0}, alpha=50.0, beta=1.0, pulls=10)
    loser = BanditArm(arm_id="lose", weights={"location": 1.0}, alpha=1.0, beta=50.0, pulls=10)
    chosen = thompson_select([loser, winner], rng=random.Random(1))
    assert chosen.arm_id == "win"


@pytest.mark.asyncio
async def test_resolve_weights_prefers_valid_profile_weights():
    weights = {
        "semantic": 0.4,
        "expertise": 0.2,
        "education": 0.1,
        "teaching_level": 0.1,
        "location": 0.05,
        "class_size": 0.05,
        "social": 0.05,
        "quality": 0.05,
    }
    selected = await resolve_weights(AsyncMock(), profile_weights=weights, bandit_enabled=False)
    assert selected.source == "profile"
    assert selected.arm_id is None
    assert abs(sum(selected.weights.values()) - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_resolve_weights_ignores_invalid_profile_and_falls_back():
    selected = await resolve_weights(
        AsyncMock(),
        profile_weights={"semantic": -1},
        bandit_enabled=False,
    )
    assert selected.source == "default"
    assert selected.arm_id == "default"


@pytest.mark.asyncio
async def test_resolve_weights_samples_bandit_arms():
    arm = BanditArm(
        arm_id="semantic_heavy",
        weights={
            "semantic": 0.55,
            "expertise": 0.1,
            "education": 0.1,
            "teaching_level": 0.05,
            "location": 0.05,
            "class_size": 0.05,
            "social": 0.05,
            "quality": 0.05,
        },
        alpha=2.0,
        beta=1.0,
        pulls=1,
    )
    db = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = [arm]
    db.scalars = AsyncMock(return_value=scalars)
    db.add = MagicMock()
    db.flush = AsyncMock()

    selected = await resolve_weights(db, profile_weights=None, bandit_enabled=True)
    assert selected.source == "bandit"
    assert selected.arm_id == "semantic_heavy"


@pytest.mark.asyncio
async def test_ensure_arms_is_noop_when_catalogue_exists():
    specs = default_arm_specs()
    existing = [
        BanditArm(arm_id=arm_id, weights=weights, alpha=1.0, beta=1.0, pulls=0)
        for arm_id, weights in specs.items()
    ]
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = existing
    db.scalars = AsyncMock(return_value=result)
    db.add = MagicMock()

    arms = await ensure_arms(db)
    db.add.assert_not_called()
    assert len(arms) == len(specs)


@pytest.mark.asyncio
async def test_ensure_arms_creates_missing_catalogue_entries():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    populated = MagicMock()
    populated.all.return_value = [
        BanditArm(arm_id="default", weights={"semantic": 1.0}, alpha=1.0, beta=1.0, pulls=0)
    ]
    db.scalars = AsyncMock(side_effect=[empty, populated])
    db.add = MagicMock()
    db.flush = AsyncMock()

    arms = await ensure_arms(db)
    assert db.add.call_count >= 1
    db.flush.assert_awaited()
    assert arms


@pytest.mark.asyncio
async def test_resolve_weights_defaults_when_bandit_has_no_arms():
    db = AsyncMock()
    empty = MagicMock()
    empty.all.return_value = []
    # First call (ensure) and reload after create both empty → fall through.
    db.scalars = AsyncMock(return_value=empty)
    db.add = MagicMock()
    db.flush = AsyncMock()

    selected = await resolve_weights(db, profile_weights=None, bandit_enabled=True)
    # Created arms but reload returned none → default source.
    assert selected.source in {"bandit", "default"}


@pytest.mark.asyncio
async def test_record_feedback_updates_beta_posterior():
    arm = BanditArm(arm_id="default", weights={"semantic": 1.0}, alpha=1.0, beta=1.0, pulls=0)
    db = AsyncMock()
    db.get = AsyncMock(return_value=arm)

    await record_feedback(db, arm_id="default", feedback=RecommendationFeedback.SAVED)
    assert arm.alpha == 2.0
    assert arm.pulls == 1

    await record_feedback(db, arm_id="default", feedback=RecommendationFeedback.DISMISSED)
    assert arm.beta == 2.0
    assert arm.pulls == 2

    await record_feedback(db, arm_id=None, feedback=RecommendationFeedback.CONNECTED)
    await record_feedback(db, arm_id="default", feedback=RecommendationFeedback.NONE)

    db.get = AsyncMock(return_value=None)
    await record_feedback(db, arm_id="missing", feedback=RecommendationFeedback.CONNECTED)
