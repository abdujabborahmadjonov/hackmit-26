"""API smoke tests for class profiles and technique search heuristics."""

from __future__ import annotations

import pytest

from app.api.technique_search import _heuristic_parse
from tests.conftest import register, requires_db


def test_heuristic_parse_broad_concept():
    result = _heuristic_parse("math", "students struggle")
    assert result.needs_follow_up
    assert result.follow_up_kind == "concept"


def test_heuristic_parse_vague_problem():
    result = _heuristic_parse("Chain rule", "students struggle")
    assert result.needs_follow_up
    assert result.follow_up_kind == "problem"


@requires_db
@pytest.mark.asyncio
async def test_create_and_list_class_profile(client):
    account = await register(client)
    headers = account["headers"]
    payload = {
        "title": "Calc I Section A",
        "subject": "calculus",
        "level": "university",
        "format": "lecture",
        "status": "planned",
        "class_size_min": 20,
        "class_size_max": 40,
        "student_background": "First-year STEM",
    }
    created = await client.post("/class-profiles", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["title"] == "Calc I Section A"
    assert body["status"] == "planned"

    listed = await client.get("/class-profiles", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json()["items"])

    promoted = await client.post(
        f"/class-profiles/{body['id']}/promote",
        json={"class_size": 32},
        headers=headers,
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["status"] == "active"
    assert promoted.json()["class_size"] == 32


@requires_db
@pytest.mark.asyncio
async def test_create_technique_and_search_run(client):
    account = await register(client)
    headers = account["headers"]
    klass = await client.post(
        "/class-profiles",
        json={
            "title": "CS101",
            "subject": "intro_cs",
            "level": "university",
            "format": "lab",
            "status": "active",
            "class_size": 28,
        },
        headers=headers,
    )
    assert klass.status_code == 201
    class_id = klass.json()["id"]

    tech = await client.post(
        "/techniques",
        json={
            "title": "Linked list walk-through",
            "summary": "Students trace pointer updates on paper before coding.",
            "steps": "1. Draw nodes.\n2. Mutate next.\n3. Compare to code.",
            "materials": "Paper",
            "class_time_minutes": 20,
            "teaching_style": "worked_examples",
            "context_subject": "intro_cs",
            "context_level": "university",
            "context_format": "lab",
            "context_class_size": 28,
            "problem_types": ["misconception", "missing_prerequisite"],
            "concept_ids": [],
            "is_draft": False,
            "is_published": True,
        },
        headers=headers,
    )
    assert tech.status_code == 201, tech.text

    ran = await client.post(
        "/technique-search/run",
        json={
            "class_profile_id": class_id,
            "concept_labels": ["Linked lists"],
            "problem_types": ["misconception"],
            "problem_text": "Students lose track of next pointers",
            "limit": 5,
        },
        headers=headers,
    )
    assert ran.status_code == 200, ran.text
    assert "items" in ran.json()
