"""Thompson-sampling bandit over discrete recommendation weight arms.

Each arm is a normalised weight dict. Feedback updates Beta(alpha, beta):
connected/saved → success, dismissed → failure. Profile-stored weights bypass
the bandit entirely when present.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import RECOMMENDATION_FACTORS, normalise_recommendation_weights, settings
from app.models.recommendation import BanditArm, RecommendationFeedback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SelectedWeights:
    weights: dict[str, float]
    arm_id: str | None
    source: str  # "profile" | "bandit" | "default"


def _emphasise(base: dict[str, float], factor: str, boost: float = 0.55) -> dict[str, float]:
    """Build an arm that puts `boost` mass on `factor`, remainder proportional."""
    rest = {k: v for k, v in base.items() if k != factor}
    rest_total = sum(rest.values()) or 1.0
    out = {factor: boost}
    share = 1.0 - boost
    for key, value in rest.items():
        out[key] = share * (value / rest_total)
    return normalise_recommendation_weights(out)


def default_arm_specs() -> dict[str, dict[str, float]]:
    base = settings.recommendation_weights
    specs: dict[str, dict[str, float]] = {"default": dict(base)}
    for factor in RECOMMENDATION_FACTORS:
        specs[f"{factor}_heavy"] = _emphasise(base, factor)
    # Balanced exploration arm: flatten slightly toward uniform.
    uniform_mix = {f: 0.5 * base[f] + 0.5 / len(RECOMMENDATION_FACTORS) for f in RECOMMENDATION_FACTORS}
    specs["explore"] = normalise_recommendation_weights(uniform_mix)
    return specs


async def ensure_arms(db: AsyncSession) -> list[BanditArm]:
    """Create missing arms from the default catalogue; leave existing posteriors."""
    specs = default_arm_specs()
    existing = {arm.arm_id: arm for arm in (await db.scalars(select(BanditArm))).all()}
    # Repair arms that were inserted with empty / invalid weight payloads.
    repaired = False
    for arm_id, arm in list(existing.items()):
        try:
            arm.weights = normalise_recommendation_weights(arm.weights or {})
        except ValueError:
            if arm_id in specs:
                arm.weights = specs[arm_id]
                repaired = True
            else:
                existing.pop(arm_id, None)
    if len(existing) >= len(specs):
        if repaired:
            await db.commit()
        return list(existing.values())

    created = False
    for arm_id, weights in specs.items():
        if arm_id in existing:
            continue
        db.add(
            BanditArm(
                arm_id=arm_id,
                weights=weights,
                alpha=1.0,
                beta=1.0,
                pulls=0,
            )
        )
        created = True
    if created or repaired:
        # Persist independently of recommendation-event logging. Otherwise a
        # later rollback in `_log_events` wipes the catalogue and every request
        # falls through to weight_source=default.
        await db.commit()
        existing = {arm.arm_id: arm for arm in (await db.scalars(select(BanditArm))).all()}
    return list(existing.values())


def thompson_select(arms: list[BanditArm], rng: random.Random | None = None) -> BanditArm:
    rng = rng or random.Random()
    best: BanditArm | None = None
    best_sample = -1.0
    for arm in arms:
        sample = rng.betavariate(max(arm.alpha, 1e-3), max(arm.beta, 1e-3))
        if sample > best_sample:
            best_sample = sample
            best = arm
    assert best is not None
    return best


async def resolve_weights(
    db: AsyncSession,
    *,
    profile_weights: dict | None,
    bandit_enabled: bool | None = None,
) -> SelectedWeights:
    """Profile prefs win; else Thompson sample; else env defaults."""
    if profile_weights:
        try:
            return SelectedWeights(
                weights=normalise_recommendation_weights(profile_weights),
                arm_id=None,
                source="profile",
            )
        except ValueError:
            logger.warning("Ignoring invalid profile recommendation_weights")

    enabled = settings.rec_bandit_enabled if bandit_enabled is None else bandit_enabled
    if enabled:
        try:
            arms = await ensure_arms(db)
            usable: list[BanditArm] = []
            for arm in arms:
                try:
                    normalise_recommendation_weights(arm.weights or {})
                    usable.append(arm)
                except ValueError:
                    continue
            if usable:
                chosen = thompson_select(usable)
                return SelectedWeights(
                    weights=normalise_recommendation_weights(chosen.weights),
                    arm_id=chosen.arm_id,
                    source="bandit",
                )
            logger.warning("Bandit catalogue empty after ensure_arms; using defaults")
        except Exception:  # pragma: no cover - never break recommendations
            logger.exception("Bandit selection failed; using default weights")

    return SelectedWeights(
        weights=settings.recommendation_weights,
        arm_id="default",
        source="default",
    )


async def record_feedback(
    db: AsyncSession,
    *,
    arm_id: str | None,
    feedback: RecommendationFeedback,
) -> None:
    """Update Beta posterior for the arm that served this recommendation."""
    if not arm_id or feedback in (RecommendationFeedback.NONE,):
        return

    arm = await db.get(BanditArm, arm_id)
    if arm is None:
        return

    if feedback in (RecommendationFeedback.SAVED, RecommendationFeedback.CONNECTED):
        arm.alpha = float(arm.alpha) + 1.0
    elif feedback == RecommendationFeedback.DISMISSED:
        arm.beta = float(arm.beta) + 1.0
    else:
        return

    arm.pulls = int(arm.pulls) + 1
