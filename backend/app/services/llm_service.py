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

from pydantic import BaseModel, Field

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


def _client() -> Any:
    if not is_enabled():
        raise LLMUnavailable(
            "Generative features need LLM_API_KEY (an Anthropic API key). "
            "Everything else works without it."
        )
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise LLMUnavailable("The 'anthropic' package is not installed") from exc
    return AsyncAnthropic(api_key=settings.llm_api_key, timeout=45.0)


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
