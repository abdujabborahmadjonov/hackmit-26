"""Connection requests: duplicates, authorisation and state transitions."""

from __future__ import annotations

import pytest

from tests.conftest import register, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_request_and_accept(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]

    created = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    incoming = (
        await client.get("/connections?direction=incoming&status=pending", headers=bob["headers"])
    ).json()
    assert incoming["total"] == 1

    accepted = await client.put(
        f"/connections/{created.json()['id']}", json={"status": "accepted"}, headers=bob["headers"]
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"


async def test_duplicate_requests_are_rejected_in_both_directions(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    alice_id = (await client.get("/auth/me", headers=alice["headers"])).json()["id"]
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]

    await client.post("/connections", json={"receiver_id": bob_id}, headers=alice["headers"])

    again = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )
    assert again.status_code == 409

    reverse = await client.post(
        "/connections", json={"receiver_id": alice_id}, headers=bob["headers"]
    )
    assert reverse.status_code == 409


async def test_cannot_connect_with_yourself(client):
    alice = await register(client)
    alice_id = (await client.get("/auth/me", headers=alice["headers"])).json()["id"]
    response = await client.post(
        "/connections", json={"receiver_id": alice_id}, headers=alice["headers"]
    )
    assert response.status_code == 400


async def test_only_the_receiver_can_accept(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]
    created = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )

    self_accept = await client.put(
        f"/connections/{created.json()['id']}",
        json={"status": "accepted"},
        headers=alice["headers"],
    )
    assert self_accept.status_code == 403


async def test_third_party_cannot_touch_a_connection(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    mallory = await register(client, first_name="Mallory")
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]
    created = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )

    assert (
        await client.put(
            f"/connections/{created.json()['id']}",
            json={"status": "accepted"},
            headers=mallory["headers"],
        )
    ).status_code == 403
    assert (
        await client.delete(f"/connections/{created.json()['id']}", headers=mallory["headers"])
    ).status_code == 403


async def test_blocking_and_withdrawing(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]
    created = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )
    connection_id = created.json()["id"]

    blocked = await client.put(
        f"/connections/{connection_id}", json={"status": "blocked"}, headers=bob["headers"]
    )
    assert blocked.json()["status"] == "blocked"

    retry = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )
    assert retry.status_code == 403

    removed = await client.delete(f"/connections/{connection_id}", headers=bob["headers"])
    assert removed.status_code == 200
    assert (await client.get("/connections", headers=bob["headers"])).json()["total"] == 0


async def test_rejected_request_can_be_reopened_by_the_other_side(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    alice_id = (await client.get("/auth/me", headers=alice["headers"])).json()["id"]
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]

    created = await client.post(
        "/connections", json={"receiver_id": bob_id}, headers=alice["headers"]
    )
    await client.put(
        f"/connections/{created.json()['id']}", json={"status": "rejected"}, headers=bob["headers"]
    )

    reopened = await client.post(
        "/connections", json={"receiver_id": alice_id}, headers=bob["headers"]
    )
    assert reopened.status_code == 201
    assert reopened.json()["status"] == "pending"
    assert reopened.json()["requester_id"] == bob_id


async def test_connection_requires_authentication(client):
    bob = await register(client)
    bob_id = (await client.get("/auth/me", headers=bob["headers"])).json()["id"]
    assert (await client.post("/connections", json={"receiver_id": bob_id})).status_code == 401
    assert (await client.get("/connections")).status_code == 401
