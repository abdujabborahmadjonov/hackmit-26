"""Basic tests for technique ranking helpers and class profiles API smoke."""

from __future__ import annotations

from app.services.technique_search_service import (
    ScoredTechnique,
    bayesian_average,
    class_context_similarity,
    mmr_rerank,
    problem_type_overlap,
    technique_matches_field,
)
from app.taxonomy import fields_compatible


class _FakeClass:
    subject = "calculus"
    level = "university"
    format = "lecture"

    def effective_class_size(self):
        return 30.0


class _FakeTechnique:
    def __init__(self, style: str, embedding=None, context_subject=None, concepts=None):
        self.teaching_style = style
        self.embedding = embedding
        self.rating_count = 0
        self.id = style
        self.context_subject = context_subject
        self.concepts = concepts or []


def test_bayesian_average_weights_similar_classes():
    # Two 5-star from similar classes beat many 2-stars from dissimilar ones.
    score = bayesian_average([(5, 1.0), (5, 0.9), (2, 0.1), (2, 0.1)])
    weak = bayesian_average([(2, 1.0), (2, 1.0), (2, 1.0), (2, 1.0)])
    assert score > weak
    assert score > 3.7


def test_problem_type_overlap():
    assert problem_type_overlap(["misconception"], ["misconception", "pacing"]) == 1.0
    assert problem_type_overlap(["misconception", "pacing"], ["engagement"]) == 0.0
    assert problem_type_overlap([], ["engagement"]) == 0.5


def test_class_context_similarity():
    searcher = _FakeClass()
    high = class_context_similarity(
        searcher, subject="calculus", level="university", format_="lecture", class_size=32
    )
    related = class_context_similarity(
        searcher, subject="mathematics", level="university", format_="lecture", class_size=32
    )
    low = class_context_similarity(
        searcher, subject="biology", level="high_school", format_="lab", class_size=120
    )
    assert high > related > low


def test_fields_compatible_same_and_related():
    assert fields_compatible("calculus", "calculus")
    assert fields_compatible("calculus", "mathematics")
    assert fields_compatible("intro_cs", "computer_science")
    assert not fields_compatible("calculus", "biology")
    assert not fields_compatible("calculus", "intro_biology")


def test_technique_matches_field_uses_context_and_concepts():
    same = _FakeTechnique("a", context_subject="calculus")
    related = _FakeTechnique("b", context_subject="mathematics")
    other = _FakeTechnique("c", context_subject="biology")
    unknown = _FakeTechnique("d", context_subject=None)
    assert technique_matches_field(same, "calculus")
    assert technique_matches_field(related, "calculus")
    assert not technique_matches_field(other, "calculus")
    assert not technique_matches_field(unknown, "calculus")


def test_mmr_prefers_style_variety():
    a = ScoredTechnique(technique=_FakeTechnique("inquiry"), score=0.9, breakdown={})
    b = ScoredTechnique(technique=_FakeTechnique("inquiry"), score=0.88, breakdown={})
    c = ScoredTechnique(technique=_FakeTechnique("lecture"), score=0.85, breakdown={})
    ranked = mmr_rerank([a, b, c], lambda_=0.5, limit=2)
    styles = {r.technique.teaching_style for r in ranked}
    assert "lecture" in styles
