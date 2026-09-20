"""Ratings: one per reviewer, automatic rollups, authorisation."""

from __future__ import annotations

import pytest

from tests.conftest import register, register_with_profile, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_rating_updates_the_profile_rollup(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer_one = await register(client, first_name="One")
    reviewer_two = await register(client, first_name="Two")

    first = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={"rating": 5, "comment": "Brilliant at scaffolding projects."},
        headers=reviewer_one["headers"],
    )
    assert first.status_code == 201
    assert first.json()["rating"] == 5
    assert first.json()["is_verified_student"] is False

    await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={"rating": 4},
        headers=reviewer_two["headers"],
    )

    profile = (await client.get(f"/profiles/{teacher['user_id']}", headers=reviewer_one["headers"])).json()
    assert profile["rating_count"] == 2
    assert profile["average_rating"] == pytest.approx(4.5)


async def test_duplicate_rating_is_rejected_but_update_works(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer = await register(client, first_name="Reviewer")

    await client.post(f"/teachers/{teacher['user_id']}/ratings", json={"rating": 5}, headers=reviewer["headers"])
    duplicate = await client.post(
        f"/teachers/{teacher['user_id']}/ratings", json={"rating": 3}, headers=reviewer["headers"]
    )
    assert duplicate.status_code == 409

    updated = await client.put(
        f"/teachers/{teacher['user_id']}/ratings",
        json={"rating": 2, "comment": "Revised after a term of working together."},
        headers=reviewer["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["rating"] == 2

    profile = (await client.get(f"/profiles/{teacher['user_id']}", headers=reviewer["headers"])).json()
    assert profile["rating_count"] == 1
    assert profile["average_rating"] == pytest.approx(2.0)


async def test_cannot_rate_yourself(client):
    teacher = await register_with_profile(client, first_name="Solo")
    response = await client.post(
        f"/teachers/{teacher['user_id']}/ratings", json={"rating": 5}, headers=teacher["headers"]
    )
    assert response.status_code == 400


async def test_rating_bounds_are_enforced(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer = await register(client)
    for value in (0, 6, -1):
        response = await client.post(
            f"/teachers/{teacher['user_id']}/ratings",
            json={"rating": value},
            headers=reviewer["headers"],
        )
        assert response.status_code == 422


async def test_rating_requires_authentication(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    response = await client.post(f"/teachers/{teacher['user_id']}/ratings", json={"rating": 5})
    assert response.status_code == 401


async def test_verified_student_rating_requires_token_and_aspects(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    student = await register(client, first_name="Student")

    created = await client.post(
        "/teachers/me/student-tokens",
        json={"duration_minutes": 60, "label": "Period 3", "max_uses": 2},
        headers=teacher["headers"],
    )
    assert created.status_code == 201
    code = created.json()["token"]
    assert "-" in code

    missing_aspects = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={"verification_token": code, "rating": 5},
        headers=student["headers"],
    )
    assert missing_aspects.status_code == 422

    bad_token = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={
            "verification_token": "AAAA-BBBB",
            "knowledge_of_material": 5,
            "presentation": 4,
            "friendliness": 5,
            "other": 4,
        },
        headers=student["headers"],
    )
    assert bad_token.status_code == 400

    rating = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={
            "verification_token": code,
            "knowledge_of_material": 5,
            "presentation": 4,
            "friendliness": 5,
            "other": 4,
            "comment": "Clear and approachable.",
        },
        headers=student["headers"],
    )
    assert rating.status_code == 201
    body = rating.json()
    assert body["is_verified_student"] is True
    assert body["rating"] == 5  # round((5+4+5+4)/4)
    assert body["knowledge_of_material"] == 5
    assert body["presentation"] == 4

    summary = (await client.get(f"/teachers/{teacher['user_id']}/ratings/summary")).json()
    assert summary["verified_student_count"] == 1
    assert summary["aspect_averages"]["knowledge_of_material"] == pytest.approx(5.0)
    assert summary["aspect_averages"]["presentation"] == pytest.approx(4.0)

    tokens = (await client.get("/teachers/me/student-tokens", headers=teacher["headers"])).json()
    assert tokens["items"][0]["use_count"] == 1
    assert tokens["items"][0]["is_active"] is True


async def test_connection_alone_does_not_verify_student(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer = await register(client, first_name="Colleague")

    created = await client.post("/connections", json={"receiver_id": teacher["user_id"]}, headers=reviewer["headers"])
    await client.put(
        f"/connections/{created.json()['id']}",
        json={"status": "accepted"},
        headers=teacher["headers"],
    )

    rating = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={"rating": 5, "comment": "We co-taught a unit."},
        headers=reviewer["headers"],
    )
    assert rating.json()["is_verified_student"] is False


async def test_student_token_revoke_and_expiry_controls(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    student = await register(client, first_name="Student")

    created = await client.post(
        "/teachers/me/student-tokens",
        json={"duration_minutes": 30, "max_uses": 1},
        headers=teacher["headers"],
    )
    token_id = created.json()["id"]
    code = created.json()["token"]

    revoked = await client.delete(f"/teachers/me/student-tokens/{token_id}", headers=teacher["headers"])
    assert revoked.status_code == 200

    rejected = await client.post(
        f"/teachers/{teacher['user_id']}/ratings",
        json={
            "verification_token": code,
            "knowledge_of_material": 5,
            "presentation": 5,
            "friendliness": 5,
            "other": 5,
        },
        headers=student["headers"],
    )
    assert rejected.status_code == 400


async def test_list_and_summary_and_delete(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewers = [await register(client, first_name=f"R{i}") for i in range(3)]
    for reviewer, score in zip(reviewers, (5, 4, 4)):
        await client.post(
            f"/teachers/{teacher['user_id']}/ratings",
            json={"rating": score},
            headers=reviewer["headers"],
        )

    listing = (await client.get(f"/teachers/{teacher['user_id']}/ratings")).json()
    assert listing["total"] == 3
    assert len(listing["items"]) == 3

    summary = (await client.get(f"/teachers/{teacher['user_id']}/ratings/summary")).json()
    assert summary["rating_count"] == 3
    assert summary["distribution"] == {"4": 2, "5": 1}
    assert summary["average_rating"] == pytest.approx(4.33, abs=0.01)
    assert summary["verified_student_count"] == 0

    deleted = await client.delete(f"/teachers/{teacher['user_id']}/ratings", headers=reviewers[0]["headers"])
    assert deleted.status_code == 200
    profile = (await client.get(f"/profiles/{teacher['user_id']}", headers=reviewers[1]["headers"])).json()
    assert profile["rating_count"] == 2
    assert profile["average_rating"] == pytest.approx(4.0)
