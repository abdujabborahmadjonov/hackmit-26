"""Unit tests for the recommendation scoring functions (no database needed)."""

from __future__ import annotations

import pytest

from app.models.profile import TeacherProfile
from app.models.recommendation import BanditArm
from app.services.bandit_service import default_arm_specs, thompson_select
from app.services.recommendation_service import (
    RecommendationItem,
    build_reasons,
    class_size_similarity,
    education_similarity,
    expertise_similarity,
    mmr_rerank,
    quality_similarity,
    score_profiles,
    semantic_similarity,
    social_similarity,
    teaching_level_similarity,
)
from app.services.relatedness_service import clear_cooccurrence_cache, combined_relatedness
from app.utils.geo import distance_similarity, haversine_km, location_similarity


def make_profile(**kwargs) -> TeacherProfile:
    defaults = dict(
        education_levels=["high_school"],
        subjects=["computer_science"],
        fields_of_expertise=[],
        teaching_levels=["intermediate"],
        teaching_methods=["project_based"],
        teaching_style="Project-based learning.",
        bio="",
        class_size=25,
        years_experience=5,
        languages=["English"],
        latitude=42.36,
        longitude=-71.06,
        location_name="Boston, Massachusetts",
        average_rating=0.0,
        rating_count=0,
        teaching_style_embedding=None,
    )
    defaults.update(kwargs)
    return TeacherProfile(**defaults)


# --- expertise ------------------------------------------------------------- #
def test_identical_expertise_scores_one():
    terms = ["python", "machine_learning", "computer_science"]
    assert expertise_similarity(terms, terms) == pytest.approx(1.0)


def test_related_expertise_scores_high():
    """Python/ML/CS vs Python/AI/CS should be a strong - not perfect - match."""
    score = expertise_similarity(
        ["python", "machine_learning", "computer_science"],
        ["python", "artificial_intelligence", "computer_science"],
    )
    assert score > 0.85
    assert score < 1.0


def test_synonyms_are_canonicalised():
    assert expertise_similarity(["ML", "CS"], ["machine_learning", "computer_science"]) == pytest.approx(1.0)


def test_unrelated_expertise_scores_low():
    assert expertise_similarity(["music"], ["chemistry"]) < 0.1


def test_empty_expertise_is_zero():
    assert expertise_similarity([], ["python"]) == 0.0
    assert expertise_similarity(None, None) == 0.0


# --- education ------------------------------------------------------------- #
def test_education_matrix_values():
    assert education_similarity(["high_school"], ["high_school"]) == 1.0
    assert education_similarity(["high_school"], ["university"]) == pytest.approx(0.3)
    assert education_similarity(["high_school"], ["elementary"]) == pytest.approx(0.2)


def test_education_uses_best_pair():
    assert education_similarity(["elementary", "university"], ["university"]) == 1.0


def test_education_overrides_are_configurable():
    overrides = {"high_school": {"university": 0.9}}
    assert education_similarity(["high_school"], ["university"], overrides) == 0.9


# --- teaching level -------------------------------------------------------- #
def test_teaching_level_similarity():
    assert teaching_level_similarity(["beginner"], ["beginner"]) == 1.0
    assert teaching_level_similarity(["beginner"], ["intermediate"]) == pytest.approx(0.5)
    assert teaching_level_similarity(["beginner"], ["advanced"]) == 0.0


# --- class size ------------------------------------------------------------ #
def test_class_size_similarity_formula():
    assert class_size_similarity(25, 25) == 1.0
    assert class_size_similarity(25, 28) == pytest.approx(1 - 3 / 28)
    assert class_size_similarity(10, 100) == pytest.approx(0.1)
    assert class_size_similarity(None, 20) == 0.0
    assert 0.0 <= class_size_similarity(1, 1000) <= 1.0


# --- location -------------------------------------------------------------- #
def test_haversine_known_distance():
    # Boston -> Cambridge is roughly 5 km.
    distance = haversine_km(42.3601, -71.0589, 42.3736, -71.1097)
    assert 3.5 < distance < 6.0


def test_distance_bands():
    assert distance_similarity(2) == 1.0
    assert distance_similarity(10) == 0.8
    assert distance_similarity(30) == 0.5
    assert distance_similarity(100) == 0.2
    assert distance_similarity(5000) == 0.0
    assert distance_similarity(None) == 0.0


def test_location_similarity_returns_distance():
    score, distance = location_similarity(42.36, -71.06, 42.37, -71.11)
    assert score == 1.0
    assert distance is not None and distance < 5
    assert location_similarity(42.36, -71.06, None, None) == (0.0, None)


# --- semantic -------------------------------------------------------------- #
def test_semantic_similarity_bounds():
    assert semantic_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert semantic_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    # Opposite vectors clamp to 0 rather than going negative.
    assert semantic_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0
    assert semantic_similarity(None, [1.0]) == 0.0


# --- combined -------------------------------------------------------------- #
def test_score_profiles_prefers_the_closer_match():
    alice = make_profile(
        subjects=["computer_science", "python"],
        fields_of_expertise=["software_engineering"],
        teaching_style_embedding=[1.0, 0.0, 0.0],
    )
    bob = make_profile(
        subjects=["computer_science", "python"],
        fields_of_expertise=["web_development"],
        class_size=28,
        latitude=42.37,
        longitude=-71.11,
        teaching_style_embedding=[0.95, 0.31, 0.0],
    )
    carol = make_profile(
        education_levels=["university"],
        subjects=["computer_science", "machine_learning"],
        fields_of_expertise=["research_methods"],
        teaching_levels=["advanced"],
        class_size=90,
        latitude=40.71,
        longitude=-74.01,
        teaching_style_embedding=[0.0, 0.0, 1.0],
    )

    bob_score = score_profiles(alice, bob).total
    carol_score = score_profiles(alice, carol).total
    assert bob_score > carol_score
    assert 0.0 <= carol_score <= bob_score <= 1.0


def test_weights_are_normalised_and_applied():
    profile = make_profile(teaching_style_embedding=[1.0, 0.0])
    weights = {
        "semantic": 1.0,
        "expertise": 0.0,
        "education": 0.0,
        "teaching_level": 0.0,
        "location": 0.0,
        "class_size": 0.0,
        "social": 0.0,
        "quality": 0.0,
    }
    breakdown = score_profiles(profile, profile, weights)
    assert breakdown.total == pytest.approx(1.0)
    assert breakdown.components["semantic"] == pytest.approx(1.0)


def test_social_and_quality_components():
    assert social_similarity(shared_neighbors=0, is_friend_of_friend=False) == 0.0
    assert social_similarity(shared_neighbors=0, is_friend_of_friend=True) == pytest.approx(0.45)
    assert social_similarity(shared_neighbors=3, is_friend_of_friend=False) > 0.7

    unrated = quality_similarity(0.0, 0)
    strong = quality_similarity(5.0, 20)
    weak = quality_similarity(5.0, 1)
    assert 0.0 <= unrated <= 1.0
    assert strong > weak > unrated


def test_mmr_prefers_diverse_second_pick():
    alice = make_profile(subjects=["computer_science"], teaching_style_embedding=[1.0, 0.0, 0.0])
    twin = make_profile(subjects=["computer_science"], teaching_style_embedding=[0.99, 0.01, 0.0])
    other = make_profile(
        subjects=["history"],
        education_levels=["high_school"],
        teaching_style_embedding=[0.0, 0.0, 1.0],
    )
    twin_bd = score_profiles(alice, twin)
    other_bd = score_profiles(alice, other)
    twin_bd.total = 0.9
    other_bd.total = 0.85
    from app.models.user import User

    user = User(email="t@example.com", password_hash="x", first_name="T", last_name="T")
    items = [
        RecommendationItem(
            profile=twin, user=user, breakdown=twin_bd, reasons=[], explanation=[]
        ),
        RecommendationItem(
            profile=other, user=user, breakdown=other_bd, reasons=[], explanation=[]
        ),
    ]
    reranked = mmr_rerank(items, lambda_=0.5, limit=2)
    assert reranked[0].profile is twin
    assert len(reranked) == 2


def test_history_social_studies_relatedness():
    clear_cooccurrence_cache()
    assert combined_relatedness("history", "social_studies") >= 0.8
    assert combined_relatedness("esl", "linguistics") >= 0.7


def test_bandit_arm_catalogue_and_thompson():
    specs = default_arm_specs()
    assert "default" in specs
    assert "semantic_heavy" in specs
    arms = [
        BanditArm(arm_id=arm_id, weights=weights, alpha=1.0, beta=1.0, pulls=0)
        for arm_id, weights in specs.items()
    ]
    import random

    chosen = thompson_select(arms, rng=random.Random(0))
    assert chosen.arm_id in specs


def test_reasons_are_human_readable_and_ordered():
    alice = make_profile(teaching_style_embedding=[1.0, 0.0])
    bob = make_profile(class_size=28, latitude=42.37, longitude=-71.11, teaching_style_embedding=[1.0, 0.0])
    breakdown = score_profiles(alice, bob)
    reasons, explanation = build_reasons(breakdown, alice, bob, max_reasons=6)

    assert reasons, "expected at least one reason"
    assert all(isinstance(reason, str) for reason in reasons)
    # Strongest contribution first.
    contributions = [entry["contribution"] for entry in explanation]
    assert contributions == sorted(contributions, reverse=True)
    joined = " | ".join(reasons)
    assert "Same education level: High School" in joined
    assert "Similar class size: 25 vs 28" in joined
    # No raw maths leaks into the display strings.
    assert "cosine" not in joined.lower()
