"""Teacher profile CRUD, validation and embedding refresh."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.profile import TeacherProfile
from tests.conftest import create_profile, register, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_create_profile_generates_an_embedding(client, db_session):
    account = await register(client)
    profile = await create_profile(client, account["headers"])

    assert profile["subjects"] == ["computer_science", "python"]
    assert profile["has_embedding"] is True

    row = await db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == profile["user_id"])
    )
    assert row is not None
    assert row.teaching_style_embedding is not None
    assert len(row.teaching_style_embedding) == 384


async def test_profile_requires_authentication(client):
    response = await client.post("/profiles", json={"bio": "anonymous"})
    assert response.status_code == 401


async def test_duplicate_profile_is_rejected(client):
    account = await register(client)
    await create_profile(client, account["headers"])
    response = await client.post("/profiles", json={"bio": "second"}, headers=account["headers"])
    assert response.status_code == 409


async def test_vocabulary_is_validated_and_normalised(client):
    account = await register(client)

    bad = await client.post(
        "/profiles",
        json={"education_levels": ["kindergarten"]},
        headers=account["headers"],
    )
    assert bad.status_code == 422

    ok = await client.post(
        "/profiles",
        # Free-text casing and synonyms are canonicalised on the way in.
        json={"subjects": ["Machine Learning", "AI"], "education_levels": ["High School"]},
        headers=account["headers"],
    )
    assert ok.status_code == 201
    assert ok.json()["subjects"] == ["machine_learning", "artificial_intelligence"]
    assert ok.json()["education_levels"] == ["high_school"]


async def test_coordinates_are_rounded_for_privacy(client):
    account = await register(client)
    profile = await create_profile(client, account["headers"], latitude=42.361234, longitude=-71.059876)
    # ~1 km precision: never a street address.
    assert profile["latitude"] == 42.36
    assert profile["longitude"] == -71.06


async def test_update_refreshes_the_embedding(client, db_session):
    account = await register(client)
    profile = await create_profile(client, account["headers"])
    before = await db_session.scalar(
        select(TeacherProfile.teaching_style_embedding).where(
            TeacherProfile.user_id == profile["user_id"]
        )
    )

    response = await client.put(
        "/profiles/me",
        json={"teaching_style": "Socratic seminars and structured debate every week."},
        headers=account["headers"],
    )
    assert response.status_code == 200
    assert response.json()["teaching_style"].startswith("Socratic")

    db_session.expire_all()
    after = await db_session.scalar(
        select(TeacherProfile.teaching_style_embedding).where(
            TeacherProfile.user_id == profile["user_id"]
        )
    )
    assert list(after) != list(before), "changing teaching style must re-embed"


async def test_update_without_semantic_fields_keeps_the_embedding(client, db_session):
    account = await register(client)
    profile = await create_profile(client, account["headers"])
    before = await db_session.scalar(
        select(TeacherProfile.teaching_style_embedding).where(
            TeacherProfile.user_id == profile["user_id"]
        )
    )

    response = await client.put("/profiles/me", json={"class_size": 31}, headers=account["headers"])
    assert response.status_code == 200
    assert response.json()["class_size"] == 31

    db_session.expire_all()
    after = await db_session.scalar(
        select(TeacherProfile.teaching_style_embedding).where(
            TeacherProfile.user_id == profile["user_id"]
        )
    )
    assert list(after) == list(before)


async def test_partial_update_leaves_other_fields_alone(client):
    account = await register(client)
    await create_profile(client, account["headers"])
    response = await client.put("/profiles/me", json={"years_experience": 9}, headers=account["headers"])
    body = response.json()
    assert body["years_experience"] == 9
    assert body["subjects"] == ["computer_science", "python"]
    assert body["class_size"] == 25


async def test_get_other_profile_and_delete_own(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_profile = await create_profile(client, bob["headers"], bio="Bob teaches physics.")

    seen = await client.get(f"/profiles/{bob_profile['user_id']}", headers=alice["headers"])
    assert seen.status_code == 200
    assert seen.json()["bio"] == "Bob teaches physics."
    assert seen.json()["user"]["first_name"] == "Bob"

    deleted = await client.delete("/profiles/me", headers=bob["headers"])
    assert deleted.status_code == 200
    assert (await client.get("/profiles/me", headers=bob["headers"])).status_code == 404
    assert (
        await client.get(f"/profiles/{bob_profile['user_id']}", headers=alice["headers"])
    ).status_code == 404


async def test_update_without_a_profile_returns_404(client):
    account = await register(client)
    response = await client.put("/profiles/me", json={"class_size": 20}, headers=account["headers"])
    assert response.status_code == 404
