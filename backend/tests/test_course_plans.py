"""Unit tests for course-plan citation validation (no LLM / DB)."""

from __future__ import annotations

import uuid

import pytest

from app.services.course_plan_service import (
    CoursePlanGenerationError,
    RetrievalBundle,
    _validate_generated,
)
from app.services.llm_service import (
    GeneratedCoursePlan,
    GeneratedPlanItem,
    GeneratedPlanSession,
    GeneratedPlanUnit,
)


class _Fake:
    def __init__(self, id):
        self.id = id


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
                            GeneratedPlanItem(
                                technique_id=str(tid), role="core"
                            )
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
    bundle = RetrievalBundle(resources=[_Fake(uuid.uuid4())], techniques=[], similar_classes=[])  # type: ignore[list-item]
    generated = GeneratedCoursePlan(
        cannot_generate=True,
        cannot_generate_reason="Too thin",
    )
    with pytest.raises(CoursePlanGenerationError, match="Too thin"):
        _validate_generated(generated, bundle)
