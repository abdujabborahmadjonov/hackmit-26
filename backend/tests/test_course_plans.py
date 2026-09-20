"""Course plan generation: validation, schemas, API (LLM mocked)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.schemas.course_plan import (
    CoursePlanGenerateRequest,
    CoursePlanItemInput,
    CoursePlanSessionInput,
    CoursePlanStructureUpdate,
    CoursePlanUnitInput,
)
from app.services import llm_service
from app.services.course_plan_service import (
    CoursePlanGenerationError,
    RetrievalBundle,
    _build_units,
    _units_from_input,
    _validate_generated,
    serialize_plan,
    serialize_summary,
)
from app.services.llm_service import (
    GeneratedCoursePlan,
    GeneratedPlanItem,
    GeneratedPlanSession,
    GeneratedPlanUnit,
)
from tests.conftest import register, register_with_profile, requires_db


class _Fake:
    def __init__(self, id, **kwargs):
        self.id = id
        for key, value in kwargs.items():
            setattr(self, key, value)


# --------------------------------------------------------------------------- #
# Pure unit tests (no DB)
# --------------------------------------------------------------------------- #


def test_validate_requires_resource_per_session():
    rid = uuid.uuid4()
    tid = uuid.uuid4()
    bundle = RetrievalBundle(
        resources=[_Fake(rid)],  # type: ignore[list-item]
        techniques=[_Fake(tid)],  # type: ignore[list-item]
        similar_classes=[],
    )
    generated = GeneratedCoursePlan(
        title="Stats",
        overview="A short course",
        units=[
            GeneratedPlanUnit(
                title="Unit 1",
                sessions=[
                    GeneratedPlanSession(
                        title="Session 1",
                        items=[
                            GeneratedPlanItem(technique_id=str(tid), role="core")
                        ],
                    )
                ],
            )
        ],
    )
    with pytest.raises(CoursePlanGenerationError, match="at least one existing resource"):
        _validate_generated(generated, bundle)


def test_validate_accepts_grounded_resource():
    rid = uuid.uuid4()
    bundle = RetrievalBundle(
        resources=[_Fake(rid)],  # type: ignore[list-item]
        techniques=[],
        similar_classes=[],
    )
    generated = GeneratedCoursePlan(
        title="Stats",
        units=[
            GeneratedPlanUnit(
                title="Unit 1",
                concept_labels=["mean"],
                sessions=[
                    GeneratedPlanSession(
                        title="Means",
                        focus="Introduce averages",
                        items=[
                            GeneratedPlanItem(resource_id=str(rid), role="core")
                        ],
                    )
                ],
            )
        ],
    )
    units = _validate_generated(generated, bundle)
    assert len(units) == 1
    assert units[0]["sessions"][0]["items"][0]["resource_id"] == rid


def test_cannot_generate_flag():
    bundle = RetrievalBundle(
        resources=[_Fake(uuid.uuid4())],  # type: ignore[list-item]
        techniques=[],
        similar_classes=[],
    )
    generated = GeneratedCoursePlan(
        cannot_generate=True,
        cannot_generate_reason="Too thin",
    )
    with pytest.raises(CoursePlanGenerationError, match="Too thin"):
        _validate_generated(generated, bundle)


def test_validate_rejects_empty_units_and_invented_ids():
    rid = uuid.uuid4()
    bundle = RetrievalBundle(
        resources=[_Fake(rid)],  # type: ignore[list-item]
        techniques=[],
        similar_classes=[],
    )
    with pytest.raises(CoursePlanGenerationError, match="no units"):
        _validate_generated(GeneratedCoursePlan(title="X", units=[]), bundle)

    fake = GeneratedCoursePlan(
        title="X",
        units=[
            GeneratedPlanUnit(
                title="U",
                sessions=[
                    GeneratedPlanSession(
                        title="S",
                        items=[
                            GeneratedPlanItem(
                                resource_id=str(uuid.uuid4()), role="core"
                            )
                        ],
                    )
                ],
            )
        ],
    )
    with pytest.raises(CoursePlanGenerationError, match="at least one existing resource"):
        _validate_generated(fake, bundle)


def test_validate_rejects_empty_resource_pool():
    generated = GeneratedCoursePlan(
        title="X",
        units=[
            GeneratedPlanUnit(
                title="U",
                sessions=[
                    GeneratedPlanSession(
                        title="S",
                        items=[GeneratedPlanItem(resource_id=str(uuid.uuid4()))],
                    )
                ],
            )
        ],
    )
    with pytest.raises(CoursePlanGenerationError, match="no matching resources"):
        _validate_generated(generated, RetrievalBundle())


def test_generated_models_coerce_lists_and_confidence():
    plan = GeneratedCoursePlan.model_validate(
        {
            "title": "Algebra",
            "overview": ["Line 1", "Line 2"],
            "cannot_generate": "false",
            "confidence": 0.4,
            "units": [
                {
                    "title": "Unit 1",
                    "objectives": ["Obj A", "Obj B"],
                    "concept_labels": "slope, intercept",
                    "sessions": [
                        {
                            "title": "S1",
                            "focus": ["focus a"],
                            "activities_summary": 12,
                            "items": [{"resource_id": "abc", "role": "core"}],
                        }
                    ],
                }
            ],
        }
    )
    assert plan.overview == "Line 1; Line 2"
    assert plan.confidence == "0.4"
    assert plan.cannot_generate is False
    assert plan.units[0].objectives == "Obj A; Obj B"
    assert plan.units[0].concept_labels == ["slope", "intercept"]
    assert plan.units[0].sessions[0].focus == "focus a"
    assert plan.units[0].sessions[0].activities_summary == "12"


def test_generate_request_validates_taxonomy():
    ok = CoursePlanGenerateRequest(
        title="Stats",
        subject="Mathematics",
        level="High School",
        format="lecture",
        duration_weeks=4,
        topic_hints=[" means ", "means", ""],
    )
    assert ok.subject == "mathematics"
    assert ok.level == "high_school"
    assert ok.topic_hints == ["means"]

    with pytest.raises(Exception):
        CoursePlanGenerateRequest(
            title="X",
            subject="not_a_real_subject",
            level="university",
            format="lecture",
            duration_weeks=2,
        )
    with pytest.raises(Exception):
        CoursePlanGenerateRequest(
            title="X",
            subject="mathematics",
            level="kindergarten",
            format="lecture",
            duration_weeks=2,
        )
    with pytest.raises(Exception):
        CoursePlanGenerateRequest(
            title="X",
            subject="mathematics",
            level="university",
            format="lecture",
            duration_weeks=2,
            class_size_min=40,
            class_size_max=10,
        )


def test_structure_update_requires_resource_on_each_session():
    with pytest.raises(CoursePlanGenerationError, match="at least one resource"):
        _units_from_input(
            [
                CoursePlanUnitInput(
                    title="U",
                    sessions=[
                        CoursePlanSessionInput(
                            title="S",
                            items=[
                                CoursePlanItemInput(
                                    technique_id=uuid.uuid4(), role="core"
                                )
                            ],
                        )
                    ],
                )
            ]
        )


def test_build_units_and_serialize():
    rid = uuid.uuid4()
    tid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    plan = SimpleNamespace(
        id=uuid.uuid4(),
        teacher_id=uuid.uuid4(),
        class_profile_id=None,
        title="Plan",
        subject="mathematics",
        level="high_school",
        format="lecture",
        status="draft",
        duration_weeks=2,
        sessions_per_week=2,
        goals="goals",
        overview="overview",
        constraints=None,
        generation_inputs={"title": "Plan"},
        similar_class_ids=[],
        units=[],
        created_at=now,
        updated_at=now,
    )
    _build_units(
        plan,  # type: ignore[arg-type]
        [
            {
                "title": "Unit 1",
                "objectives": "Learn X",
                "concept_labels": ["x"],
                "sessions": [
                    {
                        "title": "Session 1",
                        "focus": "focus",
                        "activities_summary": "do stuff",
                        "items": [
                            {
                                "role": "core",
                                "resource_id": rid,
                                "technique_id": tid,
                            }
                        ],
                    }
                ],
            }
        ],
    )
    assert len(plan.units) == 1
    assert plan.units[0].sessions[0].items[0].resource_id == rid

    # Attach joined titles for serialize_item
    item = plan.units[0].sessions[0].items[0]
    item.id = uuid.uuid4()
    item.resource = SimpleNamespace(title="Worksheet")
    item.technique = SimpleNamespace(title="Warm-up")
    plan.units[0].id = uuid.uuid4()
    plan.units[0].sessions[0].id = uuid.uuid4()

    read = serialize_plan(plan)  # type: ignore[arg-type]
    assert read.units[0].sessions[0].items[0].resource_title == "Worksheet"
    assert read.units[0].sessions[0].items[0].technique_title == "Warm-up"
    summary = serialize_summary(plan)  # type: ignore[arg-type]
    assert summary.unit_count == 1
    assert summary.title == "Plan"


def test_structure_update_schema_roundtrip():
    payload = CoursePlanStructureUpdate(
        overview="Updated",
        units=[
            CoursePlanUnitInput(
                title="U1",
                objectives="objs",
                concept_labels=["a", "a", "b"],
                sessions=[
                    CoursePlanSessionInput(
                        title="S1",
                        focus="f",
                        items=[
                            CoursePlanItemInput(
                                resource_id=uuid.uuid4(), role="assessment"
                            )
                        ],
                    )
                ],
            )
        ],
    )
    units = _units_from_input(payload.units)
    assert units[0]["concept_labels"] == ["a", "b"]
    assert units[0]["sessions"][0]["items"][0]["role"] == "assessment"


# --------------------------------------------------------------------------- #
# API integration tests (LLM mocked)
# --------------------------------------------------------------------------- #

RESOURCE = {
    "title": "Linear equations worksheet",
    "description": "Practice solving one-step and two-step equations.",
    "resource_type": "worksheet",
    "subject": "mathematics",
    "education_level": "high_school",
    "difficulty": "beginner",
    "teaching_method": "lecture_based",
    "tags": ["algebra"],
}


def _fake_outline(resource_id: str) -> GeneratedCoursePlan:
    return GeneratedCoursePlan(
        title="Algebra Sprint",
        overview="A short grounded plan.",
        confidence="medium",
        units=[
            GeneratedPlanUnit(
                title="Equations",
                objectives="Solve linear equations",
                concept_labels=["linear equations"],
                sessions=[
                    GeneratedPlanSession(
                        title="Day 1",
                        focus="One-step equations",
                        activities_summary="Warm-up then practice",
                        items=[
                            GeneratedPlanItem(
                                resource_id=resource_id, role="core"
                            )
                        ],
                    ),
                    GeneratedPlanSession(
                        title="Day 2",
                        focus="Two-step equations",
                        items=[
                            GeneratedPlanItem(
                                resource_id=resource_id, role="core"
                            )
                        ],
                    ),
                ],
            )
        ],
    )


@requires_db
@pytest.mark.integration
async def test_generate_list_get_update_structure_and_delete(client, monkeypatch):
    monkeypatch.setattr(llm_service, "is_enabled", lambda: True)
    teacher = await register_with_profile(
        client,
        first_name="Plan",
        subjects=["mathematics"],
        education_levels=["high_school"],
    )
    peer = await register(client, first_name="Peer")
    resource = (
        await client.post("/resources", json=RESOURCE, headers=peer["headers"])
    ).json()

    async def fake_generate(**kwargs):
        return _fake_outline(resource["id"])

    monkeypatch.setattr(llm_service, "generate_course_plan_outline", fake_generate)

    created = await client.post(
        "/course-plans/generate",
        json={
            "title": "Algebra Sprint",
            "subject": "mathematics",
            "level": "high_school",
            "format": "lecture",
            "duration_weeks": 2,
            "sessions_per_week": 1,
            "goals": "Solve linear equations",
            "topic_hints": ["linear equations"],
        },
        headers=teacher["headers"],
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["class_profile_id"]
    assert len(plan["units"]) == 1
    assert plan["units"][0]["sessions"][0]["items"][0]["resource_id"] == resource["id"]

    listed = await client.get("/course-plans", headers=teacher["headers"])
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    fetched = await client.get(f"/course-plans/{plan['id']}", headers=teacher["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Algebra Sprint"

    updated = await client.put(
        f"/course-plans/{plan['id']}",
        json={"title": "Algebra Sprint v2", "status": "active"},
        headers=teacher["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Algebra Sprint v2"

    structure = await client.put(
        f"/course-plans/{plan['id']}/structure",
        json={
            "overview": "Edited overview",
            "units": [
                {
                    "title": "Edited unit",
                    "objectives": "new objs",
                    "concept_labels": ["graphs"],
                    "sessions": [
                        {
                            "title": "Edited session",
                            "focus": "graphing",
                            "items": [
                                {
                                    "role": "core",
                                    "resource_id": resource["id"],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        headers=teacher["headers"],
    )
    assert structure.status_code == 200, structure.text
    body = structure.json()
    assert body["overview"] == "Edited overview"
    assert body["units"][0]["title"] == "Edited unit"

    deleted = await client.delete(
        f"/course-plans/{plan['id']}", headers=teacher["headers"]
    )
    assert deleted.status_code == 200
    assert (
        await client.get(f"/course-plans/{plan['id']}", headers=teacher["headers"])
    ).status_code == 404


@pytest.mark.integration
@requires_db
async def test_generate_is_503_without_llm(client, monkeypatch):
    monkeypatch.setattr(llm_service, "is_enabled", lambda: False)
    teacher = await register_with_profile(client, first_name="NoKey")
    response = await client.post(
        "/course-plans/generate",
        json={
            "title": "Stats",
            "subject": "mathematics",
            "level": "university",
            "format": "lecture",
            "duration_weeks": 2,
        },
        headers=teacher["headers"],
    )
    assert response.status_code == 503


@pytest.mark.integration
@requires_db
async def test_generate_returns_422_when_model_cannot_ground(client, monkeypatch):
    monkeypatch.setattr(llm_service, "is_enabled", lambda: True)
    teacher = await register_with_profile(
        client, first_name="Thin", subjects=["mathematics"]
    )
    peer = await register(client, first_name="Lib")
    await client.post("/resources", json=RESOURCE, headers=peer["headers"])

    async def refuse(**kwargs):
        return GeneratedCoursePlan(
            cannot_generate=True,
            cannot_generate_reason="Library too thin for this brief.",
        )

    monkeypatch.setattr(llm_service, "generate_course_plan_outline", refuse)
    response = await client.post(
        "/course-plans/generate",
        json={
            "title": "Sparse",
            "subject": "mathematics",
            "level": "high_school",
            "format": "lecture",
            "duration_weeks": 2,
        },
        headers=teacher["headers"],
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["cannot_generate"] is True
    assert "thin" in detail["reason"].lower()


@pytest.mark.integration
@requires_db
async def test_regenerate_plan_and_unit(client, monkeypatch):
    monkeypatch.setattr(llm_service, "is_enabled", lambda: True)
    teacher = await register_with_profile(
        client, first_name="Regen", subjects=["mathematics"]
    )
    peer = await register(client, first_name="Peer2")
    resource = (
        await client.post("/resources", json=RESOURCE, headers=peer["headers"])
    ).json()

    async def fake_generate(**kwargs):
        outline = _fake_outline(resource["id"])
        if kwargs.get("unit_focus"):
            outline.units[0].title = "Regenerated Unit"
            outline.units[0].sessions = outline.units[0].sessions[:1]
        else:
            outline.title = "Fully Regenerated"
        return outline

    monkeypatch.setattr(llm_service, "generate_course_plan_outline", fake_generate)

    created = (
        await client.post(
            "/course-plans/generate",
            json={
                "title": "Algebra Sprint",
                "subject": "mathematics",
                "level": "high_school",
                "format": "lecture",
                "duration_weeks": 2,
                "sessions_per_week": 1,
            },
            headers=teacher["headers"],
        )
    ).json()

    regenerated = await client.post(
        f"/course-plans/{created['id']}/regenerate",
        json={"duration_weeks": 3},
        headers=teacher["headers"],
    )
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["title"] == "Fully Regenerated"
    assert regenerated.json()["duration_weeks"] == 3

    unit_id = regenerated.json()["units"][0]["id"]
    unit_regen = await client.post(
        f"/course-plans/{created['id']}/units/{unit_id}/regenerate",
        headers=teacher["headers"],
    )
    assert unit_regen.status_code == 200, unit_regen.text
    assert unit_regen.json()["units"][0]["title"] == "Regenerated Unit"


@pytest.mark.integration
@requires_db
async def test_cannot_see_another_teachers_plan(client, monkeypatch):
    monkeypatch.setattr(llm_service, "is_enabled", lambda: True)
    owner = await register_with_profile(
        client, first_name="Owner", subjects=["mathematics"]
    )
    stranger = await register_with_profile(client, first_name="Stranger")
    peer = await register(client, first_name="Peer3")
    resource = (
        await client.post("/resources", json=RESOURCE, headers=peer["headers"])
    ).json()

    async def fake_generate(**kwargs):
        return _fake_outline(resource["id"])

    monkeypatch.setattr(llm_service, "generate_course_plan_outline", fake_generate)
    plan = (
        await client.post(
            "/course-plans/generate",
            json={
                "title": "Private",
                "subject": "mathematics",
                "level": "high_school",
                "format": "lecture",
                "duration_weeks": 2,
            },
            headers=owner["headers"],
        )
    ).json()

    assert (
        await client.get(f"/course-plans/{plan['id']}", headers=stranger["headers"])
    ).status_code == 404
