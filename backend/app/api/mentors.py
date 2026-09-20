"""Mentor chat: a live conversation with one educator's persona.

The transport is Server-Sent Events, so the reply appears word by word rather
than after a ten-second pause. The API stays stateless - the client sends the
conversation back on every turn, which keeps this free of a migration and
makes each request independently replayable.

Like the other generative features it needs LLM_API_KEY; without one the
endpoints return 503 and the client hides the entrance.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.profile import TeacherProfile
from app.services import llm_service, mentor_service
from app.services.llm_service import LLMUnavailable
from app.services.mentor_service import (
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_CHARS,
    Mentor,
    MentorSource,
)
from app.utils.auth import CurrentUser
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mentors", tags=["mentors"])

DB = Annotated[AsyncSession, Depends(get_db)]

# A conversation is many calls where a brief is one, so this sits above the
# /ai limit but well below the default.
mentor_rate_limit = RateLimiter("mentor_chat", 40)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A message cannot be blank")
        return value


class ChatRequest(BaseModel):
    """The whole conversation so far. The last turn must be the teacher's."""

    messages: list[ChatTurn] = Field(min_length=1, max_length=MAX_HISTORY_MESSAGES)

    @field_validator("messages")
    @classmethod
    def _ends_with_the_teacher(cls, turns: list[ChatTurn]) -> list[ChatTurn]:
        if turns[-1].role != "user":
            raise ValueError("The last message must be from you, not the mentor")
        if turns[0].role != "user":
            raise ValueError("A conversation has to open with your message")
        return turns


class MentorCard(BaseModel):
    """What the client needs to render a mentor without starting a chat."""

    slug: str
    name: str
    title: str
    institution: str
    mode: Literal["first_person", "guide"]
    pinned: bool
    location_name: str
    known_for: str
    tagline: str
    avatar_seed: str
    avatar_url: str
    synthetic: bool
    disclaimer: str
    subjects: list[str]
    years_experience: int | None
    opening_line: str
    suggested_questions: list[str]
    collaborates_on: list[str]
    sources: list[MentorSource] = Field(
        description="What a guide is allowed to draw on. Empty for a first-person persona."
    )
    has_material: bool = Field(
        description="False for a guide whose sources have not been filled in yet"
    )
    available: bool = Field(description="False when this deployment has no API key")

    @classmethod
    def of(cls, mentor: Mentor) -> MentorCard:
        return cls(
            slug=mentor.slug,
            name=mentor.name,
            title=mentor.title,
            institution=mentor.institution,
            mode=mentor.mode,
            pinned=mentor.pinned,
            location_name=mentor.location_name,
            known_for=mentor.known_for,
            tagline=mentor.tagline,
            avatar_seed=mentor.avatar_seed or mentor.name,
            avatar_url=mentor.avatar_url,
            synthetic=mentor.synthetic,
            disclaimer=mentor.disclaimer,
            subjects=mentor.teaches.subjects,
            years_experience=mentor.teaches.years_experience,
            opening_line=mentor.opening_line,
            suggested_questions=mentor.suggested_questions,
            collaborates_on=mentor.collaborates_on,
            sources=mentor.sources,
            has_material=mentor.has_material,
            available=llm_service.is_enabled(),
        )


@router.get("", response_model=list[MentorCard], summary="Educators you can talk to")
async def list_mentors() -> list[MentorCard]:
    """Always answers, key or not - `available` tells the client whether to
    offer the conversation or explain why it is off."""
    return [MentorCard.of(mentor) for mentor in mentor_service.list_mentors()]


@router.get("/{slug}", response_model=MentorCard, summary="One mentor")
async def get_mentor(slug: str) -> MentorCard:
    mentor = mentor_service.get_mentor(slug)
    if mentor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such mentor")
    return MentorCard.of(mentor)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


CITATION = re.compile(r"\[([A-Za-z][\w.-]{0,15})\]")


def _citations(reply: str, mentor: Mentor) -> tuple[list[MentorSource], list[str]]:
    """Resolve the keys the reply used, and catch any it made up.

    A guide is only trustworthy if its references are, so the server checks
    them rather than taking the model's word for it: what comes back is the
    sources actually cited, plus any key that matches nothing - which the
    client shows as unverified rather than rendering as a real reference.
    """
    if mentor.mode != "guide":
        return [], []
    by_id = {source.id: source for source in mentor.sources}
    used = dict.fromkeys(CITATION.findall(reply))  # ordered, de-duplicated
    cited = [by_id[key] for key in used if key in by_id]
    unknown = [key for key in used if key not in by_id]
    if unknown:
        logger.warning("Mentor %s cited unknown sources: %s", mentor.slug, unknown)
    return cited, unknown


@router.post(
    "/{slug}/chat",
    dependencies=[Depends(mentor_rate_limit)],
    summary="Talk to a mentor (streams)",
    description=(
        "Streams the mentor's reply as Server-Sent Events: `delta` events carry "
        "text as it is generated, then one `done` event, or an `error` event if "
        "the model drops mid-reply. Send the whole conversation each turn - the "
        "server keeps none of it."
    ),
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(slug: str, body: ChatRequest, current_user: CurrentUser, db: DB) -> StreamingResponse:
    mentor = mentor_service.get_mentor(slug)
    if mentor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such mentor")
    if not llm_service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mentor chat is not configured on this deployment.",
        )

    # The mentor answers in the teacher's context, so their profile is part of
    # the prompt. Not having one is fine - the persona asks instead.
    profile = await db.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == current_user.id)
    )
    persona = mentor_service.persona_prompt(mentor)
    viewer = mentor_service.viewer_prompt(profile, current_user.first_name)
    turns = [{"role": turn.role, "content": turn.content} for turn in body.messages]

    async def events() -> AsyncIterator[str]:
        reply: list[str] = []
        try:
            async for chunk in llm_service.stream_mentor_reply(persona, viewer, turns):
                reply.append(chunk)
                yield _sse("delta", {"text": chunk})
        except LLMUnavailable as exc:
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception as exc:  # pragma: no cover - the unexpected path
            logger.exception("Mentor chat stream failed")
            yield _sse("error", {"detail": f"The conversation dropped: {exc}"})
            return

        cited, unknown = _citations("".join(reply), mentor)
        yield _sse(
            "done",
            {
                "mentor": mentor.slug,
                "citations": [source.model_dump() for source in cited],
                "unverified": unknown,
            },
        )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Render and nginx buffer proxied responses by default, which turns
            # a live stream back into one slow blob.
            "X-Accel-Buffering": "no",
        },
    )
