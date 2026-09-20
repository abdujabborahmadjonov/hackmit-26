"""API smoke tests for class profiles, techniques, ratings, and search."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api.technique_search import _heuristic_parse
from app.services import concept_service, rating_link_service
from app.services.technique_search_service import (
    rating_summary_for,
    score_technique,
)
from tests.conftest import register, requires_db


def test_heuristic_parse_broad_concept():
    result = _heuristic_parse("math", "students struggle")
    assert result.needs_follow_up
    assert result.follow_up_kind == "concept"


def test_heuristic_parse_vague_problem():
    result = _heuristic_parse("Chain rule", "students struggle")
    assert result.needs_follow_up
    assert result.follow_up_kind == "problem"


def test_heuristic_parse_specific_query():
    result = _heuristic_parse(
        "Chain rule for composite functions",
        "Students cancel dy/dx symbols as if derivatives were fractions.",
    )
    assert result.needs_follow_up is False
    assert result.concept_chips
    assert result.problem_chips


def test_concept_slugify_and_alias_normalise():
    assert concept_service.slugify("Chain Rule", subject="calculus") == "calculus_chain_rule"
    assert concept_service.normalise_alias("  Chain   Rule ") == "chain rule"


def test_rating_link_helpers():
    token = rating_link_service.generate_rating_token()
    assert len(token) >= 16
    active = SimpleNamespace(
        is_revoked=False,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        max_uses=5,
        use_count=1,
        id="x",
        technique_id="t",
        teacher_id="u",
        class_profile_id=None,
        label="demo",
        created_at=datetime.now(UTC),
    )
    assert rating_link_service.is_active(active)
    fields = rating_link_service.link_to_read_fields(active, token=token)
    assert fields["is_active"] is True
    assert fields["rate_path"] == f"/rate/{token}"

    expired = SimpleNamespace(
        is_revoked=False,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        max_uses=None,
        use_count=0,
    )
    assert rating_link_service.is_active(expired) is False


def test_score_technique_and_rating_summary():
    searcher = SimpleNamespace(
        subject="calculus",
        level="university",
        format="lecture",
        effective_class_size=lambda: 30.0,
    )
    tech = SimpleNamespace(
        context_subject="calculus",
        context_level="university",
        context_format="lecture",
        context_class_size=28,
        problem_types=["misconception"],
        rating_count=0,
    )
    scored = score_technique(tech, searcher=searcher, problem_types=["misconception"], ratings=[])
    assert 0.0 <= scored.score <= 1.0
    assert "context_fit" in scored.breakdown

    ratings = [
        SimpleNamespace(
            rating=5,
            comment="Worked well",
            context_subject="calculus",
            context_level="university",
            context_format="lecture",
            context_class_size=30,
        ),
        SimpleNamespace(
            rating=2,
            comment=None,
            context_subject="biology",
            context_level="high_school",
            context_format="lab",
            context_class_size=100,
        ),
    ]
    summary = rating_summary_for(ratings, searcher=searcher)
    assert summary["count"] == 2
    assert summary["similar_class_count"] >= 1
    assert summary["sample_comment"] == "Worked well"


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

    got = await client.get(f"/class-profiles/{body['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]

    updated = await client.put(
        f"/class-profiles/{body['id']}",
        json={"notes": "Prefer whiteboard over slides"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["notes"] == "Prefer whiteboard over slides"

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
    tech_id = tech.json()["id"]

    listed = await client.get("/techniques?mine=true", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == tech_id for item in listed.json()["items"])

    got = await client.get(f"/techniques/{tech_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "Linked list walk-through"

    updated = await client.put(
        f"/techniques/{tech_id}",
        json={"summary": "Paper trace of pointer updates, then code."},
        headers=headers,
    )
    assert updated.status_code == 200
    assert "Paper trace" in updated.json()["summary"]

    parsed = await client.post(
        "/technique-search/parse",
        json={
            "class_profile_id": class_id,
            "concept_text": "Linked lists",
            "problem_text": "Students lose track of next pointers when mutating in place.",
            "round": 0,
        },
        headers=headers,
    )
    assert parsed.status_code == 200, parsed.text
    parse_body = parsed.json()
    assert parse_body["concept_chips"] or parse_body["needs_follow_up"]

    refined = await client.post(
        "/technique-search/refine",
        json={
            "class_profile_id": class_id,
            "concept_chips": [{"label": "Linked lists"}],
            "problem_chips": ["lose track of next pointers"],
            "problem_types": [],
            "selected_option_ids": ["misconception"],
            "round": 1,
        },
        headers=headers,
    )
    assert refined.status_code == 200, refined.text
    assert "misconception" in refined.json()["problem_types"]

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
    assert any(item["id"] == tech_id for item in ran.json()["items"])

    planning = await client.get(
        "/technique-search/planning",
        params={"class_profile_id": class_id, "concept_label": "Linked lists"},
        headers=headers,
    )
    assert planning.status_code == 200, planning.text
    assert planning.json()["concept"]["label"]


@requires_db
@pytest.mark.asyncio
async def test_tried_this_rating_link_and_student_rate(client):
    account = await register(client)
    headers = account["headers"]
    klass = await client.post(
        "/class-profiles",
        json={
            "title": "Calc lab",
            "subject": "calculus",
            "level": "university",
            "format": "lecture",
            "status": "active",
            "class_size": 30,
        },
        headers=headers,
    )
    assert klass.status_code == 201
    class_id = klass.json()["id"]

    tech = await client.post(
        "/techniques",
        json={
            "title": "Chain rule card sort",
            "summary": "Sort composite functions before differentiating.",
            "steps": "1. Sort.\n2. Differentiate.\n3. Compare.",
            "context_subject": "calculus",
            "context_level": "university",
            "context_format": "lecture",
            "context_class_size": 30,
            "problem_types": ["misconception"],
            "is_draft": False,
            "is_published": True,
        },
        headers=headers,
    )
    assert tech.status_code == 201, tech.text
    tech_id = tech.json()["id"]

    link = await client.post(
        f"/techniques/{tech_id}/tried-this",
        json={
            "class_profile_id": class_id,
            "label": "Friday section",
            "duration_minutes": 120,
            "max_uses": 3,
        },
        headers=headers,
    )
    assert link.status_code == 201, link.text
    token = link.json()["token"]
    assert token

    preview = await client.get(f"/rate/{token}")
    assert preview.status_code == 200
    assert preview.json()["id"] == tech_id

    rated = await client.post(
        f"/rate/{token}",
        json={"rating": 5, "comment": "Clear and quick"},
    )
    assert rated.status_code == 201, rated.text
    assert rated.json()["rating"] == 5

    again = await client.get(f"/techniques/{tech_id}", headers=headers)
    assert again.status_code == 200
    assert again.json()["rating_count"] >= 1


@requires_db
@pytest.mark.asyncio
async def test_delete_class_profile_and_technique(client):
    account = await register(client)
    headers = account["headers"]
    klass = await client.post(
        "/class-profiles",
        json={
            "title": "Temp class",
            "subject": "biology",
            "level": "high_school",
            "format": "lab",
            "status": "planned",
        },
        headers=headers,
    )
    assert klass.status_code == 201
    class_id = klass.json()["id"]

    tech = await client.post(
        "/techniques",
        json={
            "title": "Disposable technique",
            "summary": "Only for delete coverage.",
            "steps": "1. Do nothing.",
            "context_subject": "biology",
            "is_draft": True,
            "is_published": False,
        },
        headers=headers,
    )
    assert tech.status_code == 201
    tech_id = tech.json()["id"]

    deleted_tech = await client.delete(f"/techniques/{tech_id}", headers=headers)
    assert deleted_tech.status_code == 200

    deleted_class = await client.delete(f"/class-profiles/{class_id}", headers=headers)
    assert deleted_class.status_code == 200
