"""The demo data generator, at a size that keeps CI fast."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.connection import Connection
from app.models.profile import TeacherProfile
from app.models.rating import Rating
from app.models.resource import Resource
from app.models.user import User
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
    rows = (
        await db_session.execute(
            select(TeacherProfile.education_levels, TeacherProfile.fields_of_expertise)
        )
    ).all()
    for levels, expertise in rows:
        if "elementary" in levels:
            assert "quantum_computing" not in expertise
            assert "thesis_supervision" not in expertise

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
