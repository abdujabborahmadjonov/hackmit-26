"""Generative features, grounded in EduMatch's own data.

Everything here takes structured facts the API already computed - profiles,
component scores, shared attributes - and asks Claude to turn them into prose
or to pull structure out of a document. The model is never the source of a
fact: if it is not in the prompt, it must not appear in the output.

Disabled unless LLM_API_KEY (or ANTHROPIC_API_KEY) is set, so the rest of the
product runs unchanged without it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.taxonomy import (
    EDUCATION_LEVELS,
    TEACHING_LEVELS,
    TEACHING_METHODS,
    humanize,
)

logger = logging.getLogger(__name__)

# Claude Opus 5 with server-side refusal fallbacks: if a safety classifier
# declines, the API routes to another model rather than handing us a 200 with
# no usable content.
MODEL = "claude-opus-5"
# `betas` and `fallbacks` are only accepted on the beta namespace
# (client.beta.messages.*), not on client.messages.*.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    """No API key configured, or the provider could not be reached."""


def is_enabled() -> bool:
    return bool(settings.llm_api_key)


def _client(*, timeout: float = 45.0) -> Any:
    if not is_enabled():
        raise LLMUnavailable(
            "Generative features need LLM_API_KEY (an Anthropic API key). "
            "Everything else works without it."
        )
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise LLMUnavailable("The 'anthropic' package is not installed") from exc
    return AsyncAnthropic(api_key=settings.llm_api_key, timeout=timeout)


# --------------------------------------------------------------------------- #
# Collaboration brief
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = """You write short, concrete collaboration proposals for two teachers.

Rules:
- Use only the facts given. Never invent a subject, school, tool, or biography detail.
- Name what they would actually do together, week by week. No pleasantries, no "synergy".
- Their differences are as useful as their overlaps - say what each brings.
- If the facts are too thin for a specific plan, say what they should compare first.
- British or American spelling, whichever the profiles use. No emoji. No headings."""


def _profile_facts(label: str, profile: Any, name: str) -> str:
    bits = [
        f"{label}: {name}",
        f"  teaches: {', '.join(humanize(s) for s in (profile.subjects or [])) or 'unspecified'}",
        f"  levels: {', '.join(humanize(e) for e in (profile.education_levels or [])) or 'unspecified'}",
        f"  learner levels: {', '.join(humanize(t) for t in (profile.teaching_levels or [])) or 'unspecified'}",
        f"  methods: {', '.join(humanize(m) for m in (profile.teaching_methods or [])) or 'unspecified'}",
        f"  expertise: {', '.join(humanize(f) for f in (profile.fields_of_expertise or [])) or 'unspecified'}",
        f"  class size: {profile.class_size or 'unspecified'}",
        f"  experience: {profile.years_experience or 'unspecified'} years",
        f"  institution: {profile.institution or 'unspecified'} ({profile.location_name or 'location unspecified'})",
    ]
    if profile.teaching_style:
        bits.append(f'  describes their teaching as: "{profile.teaching_style}"')
    return "\n".join(bits)


async def collaboration_brief(
    viewer_profile: Any,
    viewer_name: str,
    match_profile: Any,
    match_name: str,
    *,
    components: dict[str, float],
    shared_terms: list[str],
    distance_km: float | None,
    resources: list[Any] | None = None,
) -> str:
    """A specific proposal for what these two should do together."""
    facts = [
        _profile_facts("Teacher A", viewer_profile, viewer_name),
        "",
        _profile_facts("Teacher B", match_profile, match_name),
        "",
        "How the matching engine scored them (0-1 per factor):",
    ]
    facts += [f"  {humanize(key)}: {value:.2f}" for key, value in components.items()]
    if shared_terms:
        facts.append(f"  shared subjects/expertise: {', '.join(humanize(t) for t in shared_terms)}")
    if distance_km is not None:
        facts.append(f"  they are {round(distance_km)} km apart")
    if resources:
        facts.append("")
        facts.append(f"Materials {match_name} has shared:")
        facts += [
            f"  - {r.title}" + (f" ({humanize(r.subject)})" if r.subject else "")
            for r in resources[:5]
        ]

    prompt = (
        "\n".join(facts)
        + "\n\nWrite 90-130 words: one sentence on why this pairing is worth their time, "
        "then a concrete plan of two or three steps they could start this term. "
        "Address them as 'you and {other}' from Teacher A's point of view.".replace(
            "{other}", match_name.split()[0]
        )
    )

    client = _client()
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=BRIEF_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Collaboration brief failed: %s", exc)
        raise LLMUnavailable(f"Could not generate the brief: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMUnavailable("The model declined to answer this one.")
    return "".join(block.text for block in response.content if block.type == "text").strip()


# --------------------------------------------------------------------------- #
# Syllabus -> profile
# --------------------------------------------------------------------------- #
class ExtractedProfile(BaseModel):
    """What a syllabus can tell us about how someone teaches."""

    subjects: list[str] = Field(
        default_factory=list,
        description="Lowercase snake_case subject slugs, e.g. computer_science, python",
    )
    education_levels: list[str] = Field(
        default_factory=list, description=f"Any of: {', '.join(EDUCATION_LEVELS)}"
    )
    teaching_levels: list[str] = Field(
        default_factory=list, description=f"Any of: {', '.join(TEACHING_LEVELS)}"
    )
    teaching_methods: list[str] = Field(
        default_factory=list, description=f"Any of: {', '.join(TEACHING_METHODS)}"
    )
    fields_of_expertise: list[str] = Field(
        default_factory=list, description="Lowercase snake_case speciality slugs"
    )
    teaching_style: str = Field(
        default="",
        description="One or two sentences, in the teacher's own voice, on how they run the class",
    )
    class_size: int | None = Field(default=None, description="Only if the document states it")
    confidence: str = Field(
        default="low", description="high, medium or low - how much the document actually supported"
    )


EXTRACT_SYSTEM = """You read a teaching document (syllabus, lesson plan, course outline) and
fill in a teacher's profile from it.

Rules:
- Only record what the document supports. Leave a field empty rather than guessing.
- Slugs are lowercase snake_case. Use the listed vocabularies exactly where one applies.
- teaching_style must paraphrase how this document says the class is run - assessment,
  activities, how students spend their time - not a generic description of the subject.
- Set confidence to low if the document is mostly administrative (dates, policies, contacts)."""


async def extract_profile_from_document(
    text: str | None = None, *, pdf: bytes | None = None
) -> ExtractedProfile:
    """Pull profile fields out of a syllabus or lesson plan.

    A PDF goes to the model as a document block rather than through a local
    parser - it handles layout, tables and scans, and saves a dependency.
    """
    if pdf is not None:
        import base64

        content: Any = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode(),
                },
            },
            {"type": "text", "text": "Fill in the profile from this document."},
        ]
    else:
        excerpt = (text or "").strip()
        if len(excerpt) < 40:
            raise LLMUnavailable("That document has too little text to read.")
        # Long documents: the front carries the description, the back policies.
        if len(excerpt) > 24000:
            excerpt = excerpt[:24000] + "\n[...truncated]"
        content = excerpt

    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=2000,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=ExtractedProfile,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Profile extraction failed: %s", exc)
        raise LLMUnavailable(f"Could not read that document: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LLMUnavailable("The model did not return a usable profile.")
    return parsed


# --------------------------------------------------------------------------- #
# Class profile + concept + technique helpers
# --------------------------------------------------------------------------- #
class ExtractedClassProfile(BaseModel):
    """Flat string-heavy schema so Anthropic structured output stays under complexity limits."""

    title: str = ""
    subject: str = ""
    level: str = ""
    format: str = ""
    class_size: str = ""
    class_size_min: str = ""
    class_size_max: str = ""
    student_background: str = ""
    constraints: str = ""
    class_length_minutes: str = ""
    technology: str = ""
    notes: str = ""
    confidence: str = "low"

    def as_api_fields(self) -> dict[str, Any]:
        """Coerce stringly numbers for the ClassProfileDraft schema."""

        def _int(value: str) -> int | None:
            cleaned = (value or "").strip()
            if not cleaned:
                return None
            try:
                return int(float(cleaned))
            except ValueError:
                return None

        return {
            "title": self.title.strip() or None,
            "subject": self.subject.strip() or None,
            "level": self.level.strip() or None,
            "format": self.format.strip() or None,
            "class_size": _int(self.class_size),
            "class_size_min": _int(self.class_size_min),
            "class_size_max": _int(self.class_size_max),
            "student_background": self.student_background.strip() or None,
            "constraints": self.constraints.strip() or None,
            "class_length_minutes": _int(self.class_length_minutes),
            "technology": self.technology.strip() or None,
            "notes": self.notes.strip() or None,
            "confidence": self.confidence.strip() or "low",
        }


CLASS_EXTRACT_SYSTEM = f"""You read a syllabus or course outline and fill a class profile.

Return ONLY a JSON object with these string keys (use "" when unknown):
title, subject, level, format, class_size, class_size_min, class_size_max,
student_background, constraints, class_length_minutes, technology, notes, confidence.

Rules:
- Only record what the document supports. Leave a field empty rather than guessing.
- subject is lowercase snake_case.
- level must be one of: {', '.join(EDUCATION_LEVELS)} when possible.
- format must be one of: lecture, lab, online, hybrid - only if clear.
- Numeric fields are digit strings.
- If enrollment is a range, fill class_size_min and class_size_max; a single number goes in class_size.
- confidence is high, medium, or low.
- No markdown fences. No commentary. JSON only."""


async def extract_class_from_document(
    text: str | None = None, *, pdf: bytes | None = None
) -> ExtractedClassProfile:
    """Extract a class profile without Anthropic structured-output schemas.

    `messages.parse` rejects even flat schemas as "too complex" for this path
    (especially with PDF document blocks), so we ask for JSON text and validate.
    """
    import json
    import re

    if pdf is not None:
        import base64

        content: Any = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode(),
                },
            },
            {"type": "text", "text": "Fill in the class profile from this document as JSON."},
        ]
    else:
        excerpt = (text or "").strip()
        if len(excerpt) < 40:
            raise LLMUnavailable("That document has too little text to read.")
        if len(excerpt) > 24000:
            excerpt = excerpt[:24000] + "\n[...truncated]"
        content = excerpt

    client = _client()
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=CLASS_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": content}],
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Class profile extraction failed: %s", exc)
        raise LLMUnavailable(f"Could not read that document: {exc}") from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMUnavailable("The model declined to answer this one.")

    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    if not raw:
        raise LLMUnavailable("The model did not return a usable class profile.")

    # Tolerate accidental markdown fences.
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Class profile JSON parse failed: %s | raw=%r", exc, raw[:500])
        raise LLMUnavailable("The model did not return usable JSON for that syllabus.") from exc

    if not isinstance(payload, dict):
        raise LLMUnavailable("The model did not return a usable class profile.")

    # Coerce non-strings to strings for the flat schema.
    normalised = {key: "" if value is None else str(value) for key, value in payload.items()}
    try:
        return ExtractedClassProfile.model_validate(normalised)
    except Exception as exc:
        raise LLMUnavailable("The model did not return a usable class profile.") from exc


class ExtractedConcepts(BaseModel):
    concepts: list[str] = Field(
        default_factory=list,
        description="Specific teaching concepts as short noun phrases",
    )


CONCEPT_EXTRACT_SYSTEM = """You extract specific teaching concepts from lecture materials.

Rules:
- Prefer concrete concepts (e.g. 'linked lists', 'chain rule') over broad fields ('math', 'CS').
- Return 5-25 concepts, deduplicated, title-case or natural phrasing.
- Skip administrative headings, dates, and grading policies."""


async def extract_concepts_from_document(
    text: str | None = None, *, pdf: bytes | None = None
) -> list[str]:
    if pdf is not None:
        import base64

        content: Any = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode(),
                },
            },
            {"type": "text", "text": "Extract the teaching concepts from this document."},
        ]
    else:
        excerpt = (text or "").strip()
        if len(excerpt) < 20:
            raise LLMUnavailable("That document has too little text to read.")
        if len(excerpt) > 24000:
            excerpt = excerpt[:24000] + "\n[...truncated]"
        content = excerpt

    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=2000,
            system=CONCEPT_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=ExtractedConcepts,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Concept extraction failed: %s", exc)
        raise LLMUnavailable(f"Could not extract concepts: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        return []
    return [c.strip() for c in parsed.concepts if c and c.strip()]


class MergeDecision(BaseModel):
    decision: str = Field(description="'merge' or 'create'")


async def decide_concept_merge(
    *,
    candidate: str,
    nearest_label: str,
    nearest_description: str | None,
    similarity: float,
) -> str:
    prompt = (
        f"Candidate concept: {candidate}\n"
        f"Nearest existing: {nearest_label}\n"
        f"Existing description: {nearest_description or '(none)'}\n"
        f"Embedding similarity: {similarity:.3f}\n\n"
        "Should we MERGE the candidate into the existing concept, or CREATE a new one? "
        "Merge only if they name the same teaching idea."
    )
    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=200,
            system="You canonicalize a teaching-concept vocabulary. Reply with merge or create.",
            messages=[{"role": "user", "content": prompt}],
            output_format=MergeDecision,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        raise LLMUnavailable(str(exc)) from exc
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        return "create"
    return "merge" if parsed.decision.strip().lower().startswith("merge") else "create"


class ParsedSearchQuery(BaseModel):
    concept_labels: list[str] = Field(default_factory=list)
    problem_summary: str = ""
    problem_types: list[str] = Field(default_factory=list)
    concept_too_broad: bool = False
    problem_too_vague: bool = False
    suggested_subconcepts: list[str] = Field(default_factory=list)
    suggested_problem_types: list[str] = Field(default_factory=list)
    follow_up_prompt: str = ""
    vague_vs_specific: str = ""


PARSE_SEARCH_SYSTEM = """You parse a teacher's classroom search into concepts and problem types.

Problem types (use exactly these slugs when applicable):
- misconception
- missing_prerequisite
- engagement
- pacing
- transfer

Rules:
- concept_labels must be specific. If the teacher wrote something broad like 'math' or 'biology',
  set concept_too_broad=true and offer 4-6 concrete suggested_subconcepts.
- If the problem is vague ('students struggle', 'it's hard'), set problem_too_vague=true,
  fill suggested_problem_types with relevant types, and write a short vague_vs_specific contrast
  (one vague example vs one specific example).
- Prefer at most one follow-up: if both are weak, prioritise the broader concept first.
- problem_types should be empty when problem_too_vague is true (wait for the follow-up)."""


async def parse_technique_search(
    *,
    concept_text: str,
    problem_text: str,
    class_subject: str,
    class_level: str,
    round_number: int = 0,
) -> ParsedSearchQuery:
    prompt = (
        f"Class subject: {class_subject}\n"
        f"Class level: {class_level}\n"
        f"Follow-up round: {round_number}\n"
        f"Concept text: {concept_text}\n"
        f"Problem text: {problem_text}\n"
    )
    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=1500,
            system=PARSE_SEARCH_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=ParsedSearchQuery,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Search parse failed: %s", exc)
        raise LLMUnavailable(f"Could not parse that search: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LLMUnavailable("The model did not return a usable parse.")
    return parsed


class ExtractedTechnique(BaseModel):
    title: str = ""
    summary: str = ""
    steps: str = ""
    materials: str = ""
    class_time_minutes: int | None = None
    teaching_style: str = ""
    problem_types: list[str] = Field(default_factory=list)
    concept_labels: list[str] = Field(default_factory=list)
    confidence: str = "low"


TECHNIQUE_DRAFT_SYSTEM = """You draft a teaching technique card from lecture slides or notes.

Rules:
- Invent a practical classroom technique grounded in the material, not a lecture summary.
- steps should be a numbered list a teacher can follow in one sitting.
- problem_types must use only: misconception, missing_prerequisite, engagement, pacing, transfer.
- concept_labels are the specific ideas the technique targets.
- Do not invent student quotes or ratings."""


async def draft_technique_from_document(
    text: str | None = None, *, pdf: bytes | None = None
) -> ExtractedTechnique:
    if pdf is not None:
        import base64

        content: Any = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode(),
                },
            },
            {"type": "text", "text": "Draft one teaching technique card from these materials."},
        ]
    else:
        excerpt = (text or "").strip()
        if len(excerpt) < 40:
            raise LLMUnavailable("That document has too little text to read.")
        if len(excerpt) > 24000:
            excerpt = excerpt[:24000] + "\n[...truncated]"
        content = excerpt

    client = _client()
    try:
        response = await client.beta.messages.parse(
            model=MODEL,
            max_tokens=2500,
            system=TECHNIQUE_DRAFT_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=ExtractedTechnique,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        raise LLMUnavailable(f"Could not draft a technique: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LLMUnavailable("The model did not return a usable technique draft.")
    return parsed


# --------------------------------------------------------------------------- #
# Mentor chat
# --------------------------------------------------------------------------- #
# Anthropic-hosted search: it runs server side, so there is no second provider
# and no key of ours in the browser.
WEB_SEARCH_TOOL = "web_search_20260209"
# A server tool can hand the turn back mid-search; each pause is one more round
# trip, and this caps how many we will follow before giving up.
MAX_PAUSE_TURNS = 3


def web_sources(message: Any) -> list[dict[str, str]]:
    """The pages a reply actually consulted, for the client to show.

    A failed search comes back as HTTP 200 with an error object where the
    result list would be, so the shape is checked rather than assumed.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        results = getattr(block, "content", None)
        if not isinstance(results, list):  # an error object, not results
            logger.info("Web search returned an error block: %s", results)
            continue
        for result in results:
            url = getattr(result, "url", "")
            if url and url not in seen:
                seen.add(url)
                found.append({"url": url, "title": getattr(result, "title", "") or url})
    return found


async def stream_mentor_reply(
    persona_prompt: str,
    viewer_prompt: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 1600,
    research: bool = False,
    max_searches: int = 6,
    on_sources: Any = None,
) -> AsyncIterator[dict]:
    """Stream one reply, as the persona, in pieces.

    Yields `{"type": "text", ...}` for prose and `{"type": "search", ...}` when the
    model goes looking something up. A search can add half a minute, and a
    spinner that says nothing for that long reads as broken - so the client
    is told what is happening rather than left guessing.

    The persona dossier is the same for every viewer, so it goes first behind a
    cache breakpoint; the viewer's own profile follows it and varies per user.

    With `research`, the model can search the web mid-answer, which lets it help
    with questions the dossier does not cover. What it finds is the persona's
    own contribution, not the educator's view - the prompt is what keeps those
    apart, and `on_sources` receives the pages consulted so the client can show
    where the researched half came from.
    """
    client = _client()
    system = [
        {"type": "text", "text": persona_prompt, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": viewer_prompt},
    ]
    tools = (
        [{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches}]
        if research
        else []
    )

    turns: list[Any] = list(messages)
    sources: list[dict[str, str]] = []
    wrote_text = False
    searched_since_text = False

    for _ in range(MAX_PAUSE_TURNS + 1):
        try:
            async with client.beta.messages.stream(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=turns,
                tools=tools,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                # Events rather than `text_stream`: a search sits between two
                # text blocks, and concatenating them gives "...my view.I then
                # looked". Citations also split prose into many text blocks
                # though, so the break goes only where a *search* interrupted
                # it - not at every block boundary.
                async for event in stream:
                    if event.type == "content_block_start":
                        kind = getattr(event.content_block, "type", None)
                        if kind == "text":
                            if wrote_text and searched_since_text:
                                yield {"type": "text", "text": "\n\n"}
                            searched_since_text = False
                        else:
                            searched_since_text = True
                            if kind == "server_tool_use":
                                yield {"type": "search"}
                    elif event.type == "input_json":
                        # The search query arrives as it is composed; show it.
                        query = getattr(event, "snapshot", None)
                        if isinstance(query, dict) and query.get("query"):
                            yield {"type": "search", "query": str(query["query"])[:120]}
                    elif event.type == "text":
                        wrote_text = True
                        yield {"type": "text", "text": event.text}
                final = await stream.get_final_message()
        except Exception as exc:
            logger.warning("Mentor chat failed: %s", exc)
            raise LLMUnavailable(f"The conversation dropped: {exc}") from exc

        for source in web_sources(final):
            if source not in sources:
                sources.append(source)

        if getattr(final, "stop_reason", None) == "refusal":
            raise LLMUnavailable("The model declined to answer this one.")

        # The search tool hit its own iteration limit; hand the turn back.
        if getattr(final, "stop_reason", None) == "pause_turn":
            turns.append({"role": "assistant", "content": final.content})
            continue
        break

    if on_sources is not None and sources:
        on_sources(sources)


# --------------------------------------------------------------------------- #
# Class plan generation (retrieve-then-generate, grounded IDs only)
# --------------------------------------------------------------------------- #


class GeneratedPlanItem(BaseModel):
    resource_id: str = ""
    technique_id: str = ""
    role: str = "core"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(x) for x in value)
    return str(value)


class GeneratedPlanSession(BaseModel):
    title: str = ""
    focus: str = ""
    activities_summary: str = ""
    items: list[GeneratedPlanItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_text_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key in ("focus", "activities_summary", "title"):
            if key in out:
                out[key] = _as_text(out.get(key))
        return out


class GeneratedPlanUnit(BaseModel):
    title: str = ""
    objectives: str = ""
    concept_labels: list[str] = Field(default_factory=list)
    sessions: list[GeneratedPlanSession] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_text_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key in ("objectives", "title"):
            if key in out:
                out[key] = _as_text(out.get(key))
        labels = out.get("concept_labels")
        if isinstance(labels, str):
            out["concept_labels"] = [
                part.strip() for part in labels.split(",") if part.strip()
            ]
        elif labels is None:
            out["concept_labels"] = []
        return out


class GeneratedCoursePlan(BaseModel):
    title: str = ""
    overview: str = ""
    units: list[GeneratedPlanUnit] = Field(default_factory=list)
    cannot_generate: bool = False
    cannot_generate_reason: str = ""
    confidence: str = "medium"

    @model_validator(mode="before")
    @classmethod
    def coerce_top_level(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        flag = out.get("cannot_generate")
        if isinstance(flag, str):
            out["cannot_generate"] = flag.strip().lower() in {"true", "1", "yes"}
        conf = out.get("confidence")
        if conf is not None and not isinstance(conf, str):
            out["confidence"] = str(conf)
        for key in ("title", "overview", "cannot_generate_reason"):
            if key in out:
                out[key] = _as_text(out.get(key))
        return out


COURSE_PLAN_SYSTEM = f"""You design high-level multi-week class plans for educators.

You receive:
- A brief describing the class the teacher wants
- Candidate RESOURCES (shared materials) with UUIDs
- Candidate TECHNIQUES (teaching strategies) with UUIDs
- Similar peer CLASS PROFILES (structure/pacing inspiration only)

Hard rules:
- Use ONLY resource_id and technique_id values from the candidate lists. Never invent UUIDs.
- Every session MUST include at least one item with a resource_id from the candidate list.
- Techniques are optional extras when a good match exists.
- Prefer pacing ideas from similar peer classes when they fit the brief.
- Keep units high-level: title, objectives, concept labels, and short session focus notes — not full lesson scripts.
- Cover approximately duration_weeks × sessions_per_week sessions, grouped into sensible units.
- Education levels must stay within: {', '.join(EDUCATION_LEVELS)}.
- When candidate resources share the brief's subject (even if titles are imperfect topic matches),
  still generate a plan and cite the best-fit resources as supporting materials. Note imperfect
  topic fit briefly in overview — do not refuse solely for imperfect topic alignment.
- Set cannot_generate=true ONLY when the candidate resource list is empty or clearly unusable
  (wrong field entirely with no subject-compatible IDs). Do not invent citations.

Return ONLY a JSON object with keys:
title, overview, units, cannot_generate, cannot_generate_reason, confidence

units is an array of {{title, objectives, concept_labels, sessions}}
sessions is an array of {{title, focus, activities_summary, items}}
items is an array of {{resource_id, technique_id, role}} where role is core|extension|assessment
Use "" for unused optional string fields. cannot_generate is a boolean.
confidence must be a string such as "high", "medium", or "low" — never a number.
"""


def _format_resource_candidates(resources: list[Any]) -> str:
    lines: list[str] = []
    for r in resources:
        lines.append(
            f"- id={r.id} | {r.title}"
            + (f" | type={r.resource_type}" if r.resource_type else "")
            + (f" | subject={r.subject}" if r.subject else "")
            + (f" | level={r.education_level}" if r.education_level else "")
        )
        if r.description:
            lines.append(f"  {str(r.description)[:180]}")
    return "\n".join(lines) if lines else "(none)"


def _format_technique_candidates(techniques: list[Any]) -> str:
    lines: list[str] = []
    for t in techniques:
        lines.append(
            f"- id={t.id} | {t.title}"
            + (f" | subject={t.context_subject}" if t.context_subject else "")
            + (f" | level={t.context_level}" if t.context_level else "")
        )
        lines.append(f"  {str(t.summary)[:180]}")
    return "\n".join(lines) if lines else "(none)"


def _format_similar_classes(classes: list[Any]) -> str:
    lines: list[str] = []
    for c in classes:
        size = c.effective_class_size() if hasattr(c, "effective_class_size") else None
        lines.append(
            f"- {c.title} | {c.subject}/{c.level}/{c.format}"
            + (f" | ~{int(size)} students" if size else "")
            + (f" | {c.class_length_minutes} min" if c.class_length_minutes else "")
        )
        if c.notes:
            lines.append(f"  notes: {str(c.notes)[:160]}")
        if c.constraints:
            lines.append(f"  constraints: {str(c.constraints)[:160]}")
    return "\n".join(lines) if lines else "(none)"


async def generate_course_plan_outline(
    *,
    brief: dict[str, Any],
    resources: list[Any],
    techniques: list[Any],
    similar_classes: list[Any],
    existing_overview: str | None = None,
    unit_focus: dict[str, Any] | None = None,
) -> GeneratedCoursePlan:
    """Produce a grounded course outline. Caller validates IDs against candidates."""
    import json
    import re

    client = _client(timeout=180.0)
    total_sessions = int(brief.get("duration_weeks", 1)) * int(
        brief.get("sessions_per_week", 1)
    )
    user_parts = [
        "CLASS BRIEF:",
        f"  title: {brief.get('title')}",
        f"  subject: {brief.get('subject')}",
        f"  level: {brief.get('level')}",
        f"  format: {brief.get('format')}",
        f"  duration_weeks: {brief.get('duration_weeks')}",
        f"  sessions_per_week: {brief.get('sessions_per_week')}",
        f"  target_session_count: ~{total_sessions}",
        f"  class_size: {brief.get('class_size') or brief.get('class_size_min') or 'unspecified'}",
        f"  goals: {brief.get('goals') or 'unspecified'}",
        f"  constraints: {brief.get('constraints') or 'none'}",
        f"  student_background: {brief.get('student_background') or 'unspecified'}",
        f"  technology: {brief.get('technology') or 'unspecified'}",
        f"  topic_hints: {', '.join(brief.get('topic_hints') or []) or 'none'}",
        "",
        "CANDIDATE RESOURCES (cite by id):",
        _format_resource_candidates(resources),
        "",
        "CANDIDATE TECHNIQUES (optional extras, cite by id):",
        _format_technique_candidates(techniques),
        "",
        "SIMILAR PEER CLASSES (pacing inspiration only):",
        _format_similar_classes(similar_classes),
    ]
    if unit_focus:
        user_parts += [
            "",
            "REGENERATE ONLY THIS UNIT (keep other units out of the response):",
            f"  unit_index: {unit_focus.get('position')}",
            f"  current_title: {unit_focus.get('title')}",
            f"  current_objectives: {unit_focus.get('objectives') or ''}",
            "Return a full plan JSON but with units containing ONLY the regenerated unit.",
        ]
    if existing_overview:
        user_parts += ["", f"Prior plan overview for continuity: {existing_overview[:800]}"]

    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=COURSE_PLAN_SYSTEM,
            messages=[{"role": "user", "content": "\n".join(user_parts)}],
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except Exception as exc:
        logger.warning("Class plan generation failed: %s", exc)
        raise LLMUnavailable(f"Class plan generation failed: {exc}") from exc

    raw = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()
    if not raw:
        raise LLMUnavailable("The model returned an empty class plan.")

    # Strip common fences / leading prose before the JSON object.
    cleaned = raw
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]

    try:
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("expected object")
        return GeneratedCoursePlan.model_validate(payload)
    except Exception as exc:
        logger.warning(
            "Class plan JSON parse failed (%s). Raw head: %s",
            exc,
            raw[:500],
        )
        raise LLMUnavailable("The model did not return a usable class plan.") from exc
