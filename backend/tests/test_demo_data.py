"""The demo data generator, at a size that keeps CI fast."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.connection import Connection
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.resource import Resource
from app.models.user import User
from app.services.demo_data_catalog import INSTITUTIONS, LEVEL_PROFILES
from app.services.demo_data_service import (
    DEMO_PASSWORD,
    DemoDataGenerator,
    GenerationCounts,
)
from app.services.recommendation_service import RecommendationService
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.integration]


@pytest.fixture
async def generated(db_session):
    generator = DemoDataGenerator(
        db_session,
        GenerationCounts(users=60, resources=120, ratings=80, connections=40, conversations=10),
        seed=7,
        batch_size=50,
    )
    return await generator.run(truncate=True)


async def test_generates_a_consistent_dataset(generated, db_session):
    assert generated.users == 60
    assert generated.profiles == 60
    assert generated.resources == 120

    assert await db_session.scalar(select(func.count()).select_from(User)) == 60
    assert await db_session.scalar(select(func.count()).select_from(TeacherProfile)) == 60
    assert await db_session.scalar(select(func.count()).select_from(Resource)) == 120
    assert await db_session.scalar(select(func.count()).select_from(Rating)) == generated.ratings
    assert (
        await db_session.scalar(select(func.count()).select_from(Connection))
        == generated.connections
    )

    missing_embeddings = await db_session.scalar(
        select(func.count())
        .select_from(TeacherProfile)
        .where(TeacherProfile.teaching_style_embedding.is_(None))
    )
    assert missing_embeddings == 0


async def test_demo_accounts_exist_and_are_documented(generated, db_session):
    assert "demo_teacher@example.com" in generated.demo_accounts
    assert DEMO_PASSWORD == "DemoPassword123!"

    alice = await db_session.scalar(select(User).where(User.email == "demo_teacher@example.com"))
    assert alice is not None
    assert alice.first_name == "Alice"
    assert alice.password_hash.startswith("$argon2")


async def test_content_is_internally_consistent(generated, db_session):
    """Elementary teachers never get graduate-level expertise, and vice versa."""
    graduate_only = {"quantum_computing", "thesis_supervision", "grant_writing", "deep_learning"}
    rows = (
        await db_session.execute(
            select(
                TeacherProfile.education_levels,
                TeacherProfile.fields_of_expertise,
                TeacherProfile.class_size,
            )
        )
    ).all()
    for levels, expertise, class_size in rows:
        if "elementary" in levels:
            assert not (graduate_only & set(expertise or []))
            assert class_size is None or class_size <= 30
        if levels == ["graduate"]:
            assert class_size is None or class_size <= 30

    resources = (
        await db_session.execute(
            select(Resource.education_level, Resource.difficulty).limit(200)
        )
    ).all()
    for level, difficulty in resources:
        if level == "elementary":
            assert difficulty == "beginner"
        if level == "graduate":
            assert difficulty == "advanced"


async def test_profiles_have_rich_prose_and_real_institutions(generated, db_session):
    rows = (
        await db_session.execute(
            select(
                TeacherProfile.bio,
                TeacherProfile.teaching_style,
                TeacherProfile.institution,
                TeacherProfile.location_name,
            )
        )
    ).all()
    bios = [bio for bio, _, _, _ in rows if bio]
    styles = [style for _, style, _, _ in rows if style]
    assert bios
    assert sum(len(b) for b in bios) / len(bios) >= 120
    assert sum(len(s) for s in styles) / len(styles) >= 80

    # Majority of institutions should come from the curated city catalogs,
    # not the "{town} High School" fallback templates.
    catalog_names = {
        name
        for city_catalog in INSTITUTIONS.values()
        for names in city_catalog.values()
        for name in names
    }
    known = sum(1 for _, _, institution, _ in rows if institution in catalog_names)
    assert known / len(rows) >= 0.7

    cities = {location for _, _, _, location in rows if location}
    assert len(cities) >= 8


async def test_subject_expertise_stays_coherent(generated, db_session):
    """CS teachers should usually land software / programming expertise, not grant writing."""
    rows = (
        await db_session.execute(
            select(TeacherProfile.subjects, TeacherProfile.fields_of_expertise)
        )
    ).all()
    cs_rows = [
        (subjects, expertise) for subjects, expertise in rows if "computer_science" in (subjects or [])
    ]
    assert cs_rows
    coherent = 0
    cs_expertise = {
        "software_engineering",
        "python",
        "web_development",
        "robotics",
        "programming",
        "data_science",
        "machine_learning",
        "curriculum_design",
        "exam_preparation",
        "maker_education",
        "ap_ib_programmes",
        "undergraduate_research",
        "assessment_design",
        "open_educational_resources",
        "industry_partnerships",
        "college_counseling",
        "debate",
    }
    for _, expertise in cs_rows:
        if set(expertise or []) & cs_expertise:
            coherent += 1
    assert coherent / len(cs_rows) >= 0.7


async def test_rating_rollups_match_the_ratings_table(generated, db_session):
    rows = (
        await db_session.execute(
            select(
                TeacherProfile.user_id, TeacherProfile.average_rating, TeacherProfile.rating_count
            ).where(TeacherProfile.rating_count > 0).limit(5)
        )
    ).all()
    assert rows, "expected some rated teachers"
    for user_id, average, count in rows:
        actual = (
            await db_session.execute(
                select(func.avg(Rating.rating), func.count(Rating.id)).where(
                    Rating.teacher_id == user_id
                )
            )
        ).one()
        assert count == actual[1]
        assert average == pytest.approx(float(actual[0]), abs=0.01)


async def test_alice_recommendation_scenario(generated, db_session):
    """The scripted demo: Alice's top match is Bob, ahead of Carol."""
    alice = await db_session.scalar(select(User).where(User.email == "demo_teacher@example.com"))
    result = await RecommendationService(db_session).recommend(alice.id, limit=10)

    names = [item.user.first_name for item in result.items]
    assert names[0] == "Bob", f"expected Bob first, got {names}"
    assert "Carol" not in names[:1]
    if "Carol" in names:
        assert names.index("Bob") < names.index("Carol")
    assert result.items[0].breakdown.total > 0.7
    assert result.items[0].reasons


async def test_level_profiles_cover_all_education_bands():
    assert set(LEVEL_PROFILES) == {
        "elementary",
        "middle_school",
        "high_school",
        "university",
        "graduate",
        "adult_education",
    }
    for spec in LEVEL_PROFILES.values():
        assert spec["method_weights"]
        assert sum(spec["method_weights"].values()) > 0
        assert spec["institution_band"] in {"k12", "higher", "adult"}
