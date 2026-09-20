"""Discussion forum: topics, replies, authorship ACL."""

from __future__ import annotations

import pytest

from tests.conftest import register, requires_db

pytestmark = [requires_db, pytest.mark.integration]


async def test_create_and_list_topics(client):
    alice = await register(client, first_name="Alice")
    created = await client.post(
        "/forum/topics",
        json={
            "title": "Anyone co-planning a project-based CS unit?",
            "body": "Looking for a partner to swap rubrics this term.",
            "category": "collaboration",
        },
        headers=alice["headers"],
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"].startswith("Anyone co-planning")
    assert body["category"] == "collaboration"
    assert body["reply_count"] == 0
    assert body["author"]["first_name"] == "Alice"

    listed = await client.get("/forum/topics", headers=alice["headers"])
    assert listed.status_code == 200
    data = listed.json()
    assert data["total"] >= 1
    assert any(item["id"] == body["id"] for item in data["items"])


async def test_filter_topics_by_category_and_search(client):
    alice = await register(client, first_name="Alice")
    await client.post(
        "/forum/topics",
        json={
            "title": "Chromebook lab tips",
            "body": "How do you manage device carts?",
            "category": "technology",
        },
        headers=alice["headers"],
    )
    await client.post(
        "/forum/topics",
        json={
            "title": "Co-teaching algebra",
            "body": "Looking for a planning partner.",
            "category": "collaboration",
        },
        headers=alice["headers"],
    )

    tech = (
        await client.get("/forum/topics", params={"category": "technology"}, headers=alice["headers"])
    ).json()
    assert all(item["category"] == "technology" for item in tech["items"])

    search = (
        await client.get("/forum/topics", params={"q": "algebra"}, headers=alice["headers"])
    ).json()
    assert search["total"] >= 1
    assert any("algebra" in item["title"].lower() for item in search["items"])


async def test_reply_updates_counts_and_activity(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    topic_id = (
        await client.post(
            "/forum/topics",
            json={"title": "Share your favorite warm-up", "body": "Mine is a 3-minute puzzle."},
            headers=alice["headers"],
        )
    ).json()["id"]

    reply = await client.post(
        f"/forum/topics/{topic_id}/posts",
        json={"content": "We use exit tickets as warm-ups the next day."},
        headers=bob["headers"],
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["author"]["first_name"] == "Bob"

    topic = (await client.get(f"/forum/topics/{topic_id}", headers=alice["headers"])).json()
    assert topic["reply_count"] == 1

    posts = (
        await client.get(f"/forum/topics/{topic_id}/posts", headers=alice["headers"])
    ).json()
    assert posts["total"] == 1
    assert posts["items"][0]["content"].startswith("We use exit tickets")


async def test_only_author_can_edit_or_delete_topic(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    topic_id = (
        await client.post(
            "/forum/topics",
            json={"title": "Original title here", "body": "Original body content."},
            headers=alice["headers"],
        )
    ).json()["id"]

    forbidden = await client.put(
        f"/forum/topics/{topic_id}",
        json={"title": "Hijacked title here"},
        headers=bob["headers"],
    )
    assert forbidden.status_code == 403

    updated = await client.put(
        f"/forum/topics/{topic_id}",
        json={"title": "Updated title goes here"},
        headers=alice["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated title goes here"

    assert (
        await client.delete(f"/forum/topics/{topic_id}", headers=bob["headers"])
    ).status_code == 403
    deleted = await client.delete(f"/forum/topics/{topic_id}", headers=alice["headers"])
    assert deleted.status_code == 200
    assert (
        await client.get(f"/forum/topics/{topic_id}", headers=alice["headers"])
    ).status_code == 404


async def test_only_author_can_edit_or_delete_post(client):
    alice = await register(client, first_name="Alice")
    bob = await register(client, first_name="Bob")
    topic_id = (
        await client.post(
            "/forum/topics",
            json={"title": "Need feedback on a unit plan", "body": "Attached outline in text."},
            headers=alice["headers"],
        )
    ).json()["id"]
    post_id = (
        await client.post(
            f"/forum/topics/{topic_id}/posts",
            json={"content": "Happy to take a look this weekend."},
            headers=bob["headers"],
        )
    ).json()["id"]

    assert (
        await client.put(
            f"/forum/posts/{post_id}",
            json={"content": "Nope"},
            headers=alice["headers"],
        )
    ).status_code == 403

    edited = await client.put(
        f"/forum/posts/{post_id}",
        json={"content": "Happy to review your outline on Monday."},
        headers=bob["headers"],
    )
    assert edited.status_code == 200
    assert "Monday" in edited.json()["content"]

    assert (
        await client.delete(f"/forum/posts/{post_id}", headers=alice["headers"])
    ).status_code == 403
    assert (
        await client.delete(f"/forum/posts/{post_id}", headers=bob["headers"])
    ).status_code == 200
    topic = (await client.get(f"/forum/topics/{topic_id}", headers=alice["headers"])).json()
    assert topic["reply_count"] == 0


async def test_forum_requires_authentication(client):
    assert (await client.get("/forum/topics")).status_code == 401
    assert (
        await client.post(
            "/forum/topics",
            json={"title": "Unauthed topic title", "body": "Should not work."},
        )
    ).status_code == 401


async def test_empty_reply_rejected(client):
    alice = await register(client)
    topic_id = (
        await client.post(
            "/forum/topics",
            json={"title": "A valid topic title", "body": "A valid topic body."},
            headers=alice["headers"],
        )
    ).json()["id"]
    response = await client.post(
        f"/forum/topics/{topic_id}/posts",
        json={"content": ""},
        headers=alice["headers"],
    )
    assert response.status_code == 422
