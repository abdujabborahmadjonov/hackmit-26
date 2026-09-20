"""Resource metadata, uploads, ownership checks and recommendations."""

from __future__ import annotations

import io

import pytest

from tests.conftest import register, register_with_profile, requires_db

pytestmark = [requires_db, pytest.mark.integration]

RESOURCE = {
    "title": "Intro to Python Functions - Project Pack",
    "description": "A three-lesson project where students build a text adventure.",
    "resource_type": "project_brief",
    "subject": "computer_science",
    "education_level": "high_school",
    "difficulty": "beginner",
    "teaching_method": "project_based",
    "tags": ["python", "functions"],
    "required_materials": ["Laptops", "Internet Access"],
}


async def test_create_and_fetch_resource(client):
    account = await register(client)
    created = await client.post("/resources", json=RESOURCE, headers=account["headers"])
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == RESOURCE["title"]
    assert body["subject"] == "computer_science"
    assert body["required_materials"] == ["laptops", "internet_access"]
    assert body["owner_id"] == (await client.get("/auth/me", headers=account["headers"])).json()["id"]

    fetched = await client.get(f"/resources/{body['id']}", headers=account["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_resource_creation_requires_auth(client):
    assert (await client.post("/resources", json=RESOURCE)).status_code == 401


async def test_invalid_vocabulary_is_rejected(client):
    account = await register(client)
    response = await client.post(
        "/resources", json={**RESOURCE, "difficulty": "impossible"}, headers=account["headers"]
    )
    assert response.status_code == 422


async def test_filters_and_search(client):
    account = await register(client)
    await client.post("/resources", json=RESOURCE, headers=account["headers"])
    await client.post(
        "/resources",
        json={
            **RESOURCE,
            "title": "Cell Division Worksheet",
            "description": "Label the phases of mitosis from microscope images.",
            "subject": "biology",
            "resource_type": "worksheet",
            "teaching_method": "inquiry_based",
            "tags": ["mitosis"],
            "required_materials": ["microscope", "slides"],
        },
        headers=account["headers"],
    )

    by_subject = (await client.get("/resources?subject=biology")).json()
    assert by_subject["total"] == 1
    assert by_subject["items"][0]["resource"]["title"] == "Cell Division Worksheet"

    by_tag = (await client.get("/resources?tags=python")).json()
    assert by_tag["total"] == 1

    by_material = (await client.get("/resources?required_materials=laptops")).json()
    assert by_material["total"] == 1
    assert by_material["items"][0]["resource"]["subject"] == "computer_science"

    search_by_material = (await client.get("/search/resources?required_materials=microscope")).json()
    assert search_by_material["total"] == 1
    assert search_by_material["items"][0]["resource"]["subject"] == "biology"

    semantic = (await client.get("/resources?query=students build a text adventure game")).json()
    assert semantic["items"][0]["resource"]["subject"] == "computer_science"


async def test_only_the_owner_can_update_or_delete(client):
    owner = await register(client, first_name="Owner")
    stranger = await register(client, first_name="Stranger")
    resource_id = (
        await client.post("/resources", json=RESOURCE, headers=owner["headers"])
    ).json()["id"]

    forbidden = await client.put(
        f"/resources/{resource_id}", json={"title": "Hijacked"}, headers=stranger["headers"]
    )
    assert forbidden.status_code == 403
    assert (
        await client.delete(f"/resources/{resource_id}", headers=stranger["headers"])
    ).status_code == 403

    updated = await client.put(
        f"/resources/{resource_id}",
        json={"title": "Updated Project Pack", "difficulty": "intermediate"},
        headers=owner["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated Project Pack"
    assert updated.json()["difficulty"] == "intermediate"

    deleted = await client.delete(f"/resources/{resource_id}", headers=owner["headers"])
    assert deleted.status_code == 200
    assert (await client.get(f"/resources/{resource_id}")).status_code == 404


async def test_upload_accepts_allowed_types(client):
    account = await register(client)
    files = {"file": ("lesson.pdf", io.BytesIO(b"%PDF-1.4 fake pdf bytes"), "application/pdf")}
    data = {
        "title": "Uploaded Lesson Plan",
        "description": "Ratios and proportions",
        "subject": "mathematics",
        "education_level": "middle_school",
        "resource_type": "lesson_plan",
        "tags": "ratios,proportions",
        "required_materials": "calculators, graph paper",
    }
    response = await client.post(
        "/resources/upload", files=files, data=data, headers=account["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["file_url"].endswith(".pdf")
    assert body["mime_type"] == "application/pdf"
    assert body["file_size_bytes"] == len(b"%PDF-1.4 fake pdf bytes")
    assert body["tags"] == ["ratios", "proportions"]
    assert body["required_materials"] == ["calculators", "graph_paper"]


async def test_upload_rejects_disallowed_types(client):
    account = await register(client)
    files = {"file": ("payload.exe", io.BytesIO(b"MZ binary"), "application/octet-stream")}
    response = await client.post(
        "/resources/upload",
        files=files,
        data={"title": "Definitely a lesson plan"},
        headers=account["headers"],
    )
    assert response.status_code == 415


async def test_upload_rejects_oversized_files(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_mb", 0.0001)
    account = await register(client)
    files = {"file": ("big.txt", io.BytesIO(b"x" * 5000), "text/plain")}
    response = await client.post(
        "/resources/upload", files=files, data={"title": "Too large a file"}, headers=account["headers"]
    )
    assert response.status_code == 413


async def test_recommended_resources_match_the_profile(client):
    teacher = await register_with_profile(
        client,
        first_name="Alice",
        subjects=["computer_science", "python"],
        education_levels=["high_school"],
        teaching_methods=["project_based"],
        teaching_style="Project-based computer science with team software builds.",
    )
    author = await register(client, first_name="Author")
    await client.post("/resources", json=RESOURCE, headers=author["headers"])
    await client.post(
        "/resources",
        json={
            **RESOURCE,
            "title": "Baroque Music Listening Guide",
            "description": "Listening journal prompts for Bach and Vivaldi.",
            "subject": "music",
            "education_level": "elementary",
            "teaching_method": "discussion_based",
            "tags": ["baroque"],
        },
        headers=author["headers"],
    )

    response = await client.get("/resources/recommended", headers=teacher["headers"])
    assert response.status_code == 200
    items = response.json()
    assert items[0]["resource"]["subject"] == "computer_science"
    assert items[0]["match_score"] >= items[-1]["match_score"]
    assert any("Computer Science" in reason for reason in items[0]["reasons"])


async def test_recommended_resources_need_a_profile(client):
    account = await register(client)
    response = await client.get("/resources/recommended", headers=account["headers"])
    assert response.status_code == 400
