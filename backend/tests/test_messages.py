"""Messaging: conversation creation, delivery and participant-only access."""

from __future__ import annotations

import pytest

from tests.conftest import register, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def _user_id(client, account) -> str:
    return (await client.get("/auth/me", headers=account["headers"])).json()["id"]


async def test_start_conversation_with_first_message(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = await _user_id(client, bob)

    created = await client.post(
        "/messages/conversations",
        json={"participant_id": bob_id, "content": "Hi! Saw we both teach project-based CS."},
        headers=alice["headers"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert {p["first_name"] for p in body["participants"]} == {"Alice", "Bob"}
    assert body["last_message"]["content"].startswith("Hi!")

    bob_view = (await client.get("/messages/conversations", headers=bob["headers"])).json()
    assert bob_view["total"] == 1
    assert bob_view["items"][0]["unread_count"] == 1


async def test_conversations_are_reused(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = await _user_id(client, bob)

    first = await client.post(
        "/messages/conversations", json={"participant_id": bob_id}, headers=alice["headers"]
    )
    second = await client.post(
        "/messages/conversations",
        json={"participant_id": bob_id, "content": "Following up"},
        headers=alice["headers"],
    )
    assert first.json()["id"] == second.json()["id"]


async def test_cannot_message_yourself(client):
    alice = await register(client)
    alice_id = await _user_id(client, alice)
    response = await client.post(
        "/messages/conversations", json={"participant_id": alice_id}, headers=alice["headers"]
    )
    assert response.status_code == 400


async def test_send_and_read_messages(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = await _user_id(client, bob)
    conversation_id = (
        await client.post(
            "/messages/conversations",
            json={"participant_id": bob_id, "content": "First"},
            headers=alice["headers"],
        )
    ).json()["id"]

    reply = await client.post(
        f"/messages/conversations/{conversation_id}/messages",
        json={"content": "Second"},
        headers=bob["headers"],
    )
    assert reply.status_code == 201

    messages = (
        await client.get(
            f"/messages/conversations/{conversation_id}/messages", headers=alice["headers"]
        )
    ).json()
    assert messages["total"] == 2
    assert [m["content"] for m in messages["items"]] == ["Second", "First"]  # newest first
    assert messages["items"][0]["read_at"] is None

    marked = await client.post(
        f"/messages/conversations/{conversation_id}/read", headers=alice["headers"]
    )
    assert marked.status_code == 200
    after = (
        await client.get(
            f"/messages/conversations/{conversation_id}/messages", headers=alice["headers"]
        )
    ).json()
    assert after["items"][0]["read_at"] is not None
    # Alice's own message stays unread from her point of view.
    assert after["items"][1]["read_at"] is None


async def test_non_participants_are_blocked(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    mallory = await register(client, first_name="Mallory")
    bob_id = await _user_id(client, bob)
    conversation_id = (
        await client.post(
            "/messages/conversations",
            json={"participant_id": bob_id, "content": "Private"},
            headers=alice["headers"],
        )
    ).json()["id"]

    assert (
        await client.get(
            f"/messages/conversations/{conversation_id}/messages", headers=mallory["headers"]
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/messages/conversations/{conversation_id}/messages",
            json={"content": "Let me in"},
            headers=mallory["headers"],
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/messages/conversations/{conversation_id}/read", headers=mallory["headers"]
        )
    ).status_code == 403


async def test_messaging_requires_authentication(client):
    alice = await register(client)
    alice_id = await _user_id(client, alice)
    assert (
        await client.post("/messages/conversations", json={"participant_id": alice_id})
    ).status_code == 401
    assert (await client.get("/messages/conversations")).status_code == 401


async def test_empty_message_is_rejected(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    bob_id = await _user_id(client, bob)
    conversation_id = (
        await client.post(
            "/messages/conversations", json={"participant_id": bob_id}, headers=alice["headers"]
        )
    ).json()["id"]

    response = await client.post(
        f"/messages/conversations/{conversation_id}/messages",
        json={"content": ""},
        headers=alice["headers"],
    )
    assert response.status_code == 422
