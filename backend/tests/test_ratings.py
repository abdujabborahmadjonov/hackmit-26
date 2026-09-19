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

    profile = (
        await client.get(f"/profiles/{teacher['user_id']}", headers=reviewer_one["headers"])
    ).json()
    assert profile["rating_count"] == 2
    assert profile["average_rating"] == pytest.approx(4.5)


async def test_duplicate_rating_is_rejected_but_update_works(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer = await register(client, first_name="Reviewer")

    await client.post(
        f"/teachers/{teacher['user_id']}/ratings", json={"rating": 5}, headers=reviewer["headers"]
    )
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

    profile = (
        await client.get(f"/profiles/{teacher['user_id']}", headers=reviewer["headers"])
    ).json()
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


async def test_connected_reviewers_are_flagged_as_verified(client):
    teacher = await register_with_profile(client, first_name="Teacher")
    reviewer = await register(client, first_name="Colleague")

    created = await client.post(
        "/connections", json={"receiver_id": teacher["user_id"]}, headers=reviewer["headers"]
    )
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
    assert rating.json()["is_verified_student"] is True


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

    deleted = await client.delete(
        f"/teachers/{teacher['user_id']}/ratings", headers=reviewers[0]["headers"]
    )
    assert deleted.status_code == 200
    profile = (
        await client.get(f"/profiles/{teacher['user_id']}", headers=reviewers[1]["headers"])
    ).json()
    assert profile["rating_count"] == 2
    assert profile["average_rating"] == pytest.approx(4.0)
