"""Recommendation payloads - including the "Why this match?" breakdown."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import ProfileSummary


class MatchReason(BaseModel):
    """One human-readable factor behind a recommendation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "factor": "semantic",
                "label": "92% similarity in teaching philosophy",
                "score": 0.92,
                "weight": 0.30,
            }
        }
    )

    factor: str = Field(
        description=(
            "semantic | expertise | education | teaching_level | location | "
            "class_size | social | quality"
        )
    )
    label: str = Field(description="Ready-to-display explanation")
    score: float = Field(ge=0.0, le=1.0, description="Component score, 0-1")
    weight: float = Field(ge=0.0, le=1.0, description="Weight this component carries")
    contribution: float = Field(ge=0.0, le=1.0, description="score * weight")


class Recommendation(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "teacher": {
                    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "first_name": "Bob",
                    "last_name": "Martinez",
                    "location_name": "Cambridge, Massachusetts",
                    "subjects": ["computer_science", "python"],
                },
                "match_score": 0.94,
                "reasons": [
                    "92% similarity in teaching philosophy",
                    "Shared subjects: Computer Science, Python",
                    "Same education level: High School",
                    "Similar class size: 25 vs 28",
                    "Located 8 km away",
                ],
            }
        }
    )

    teacher: ProfileSummary
    match_score: float = Field(ge=0.0, le=1.0)
    components: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Every component score, 0-1, keyed by factor. Unlike `explanation` "
            "this is complete - including factors too weak to be worth showing - "
            "so a client can re-rank under different weights without another "
            "round trip."
        ),
    )
    reasons: list[str] = Field(default_factory=list, description="Short display strings")
    explanation: list[MatchReason] = Field(
        default_factory=list, description="Structured breakdown for a 'Why this match?' panel"
    )
    distance_km: float | None = None


class RecommendationResponse(BaseModel):
    items: list[Recommendation]
    generated_for: uuid.UUID
    candidate_pool_size: int = Field(
        description="How many profiles were scored before the top-N cut"
    )
    took_ms: float
    weights: dict[str, float]
    bandit_arm_id: str | None = None
    weight_source: str = Field(
        default="default",
        description="profile | bandit | default — where the weights came from",
    )


class RecommendationWeightsUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "weights": {
                    "semantic": 0.3,
                    "expertise": 0.2,
                    "education": 0.15,
                    "teaching_level": 0.15,
                    "location": 0.1,
                    "class_size": 0.1,
                    "social": 0.08,
                    "quality": 0.07,
                }
            }
        }
    )

    weights: dict[str, float] = Field(description="Factor weights; renormalised server-side")


class RecommendationWeightsRead(BaseModel):
    weights: dict[str, float]
    saved: bool = Field(description="True when personal profile weights are stored")
    source: str
    bandit_arm_id: str | None = None


class RecommendationFeedbackRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"feedback": "saved"}})

    feedback: str = Field(description="none | saved | dismissed | connected")
