#!/usr/bin/env python3
"""Talk to a mentor from the terminal - no database, no login, no frontend.

The HTTP endpoint needs a registered user and their profile, which means
Postgres. The persona does not: it is a system prompt and a stream. This drives
that directly, so you can hear how a persona sounds while you are still writing
its dossier.

    python scripts/chat_with_mentor.py                    # the pinned mentor
    python scripts/chat_with_mentor.py --mentor elena-vasquez
    python scripts/chat_with_mentor.py --as "Alice, teaches high school CS"

Needs LLM_API_KEY (or ANTHROPIC_API_KEY) in the environment or in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.mentors import _citations  # noqa: E402
from app.services import llm_service, mentor_service  # noqa: E402
from app.services.llm_service import LLMUnavailable  # noqa: E402
from app.services.mentor_service import MAX_HISTORY_MESSAGES  # noqa: E402

DIM, BOLD, CITE, WARN, OFF = "\033[2m", "\033[1m", "\033[36m", "\033[33m", "\033[0m"


def _viewer(description: str | None) -> str:
    """Stand in for the profile the API would have loaded."""
    if not description:
        return mentor_service.viewer_prompt(None, "a teacher")
    return (
        f"You are talking to {description} - a fellow teacher on EduMatch. "
        "Use this to make your answers land in their context."
    )


async def converse(slug: str | None, viewer_description: str | None) -> int:
    mentor = mentor_service.get_mentor(slug) if slug else mentor_service.list_mentors()[0]
    if mentor is None:
        available = ", ".join(m.slug for m in mentor_service.list_mentors())
        print(f"No mentor '{slug}'. Try: {available}", file=sys.stderr)
        return 1
    if not llm_service.is_enabled():
        print(
            "Set LLM_API_KEY (an Anthropic API key) in backend/.env or the environment.",
            file=sys.stderr,
        )
        return 1

    label = f"Guide to {mentor.name}" if mentor.mode == "guide" else mentor.name
    print(f"\n{BOLD}{label}{OFF} {DIM}· {mentor.title}, {mentor.institution}{OFF}")
    if mentor.mode == "guide":
        print(
            f"{DIM}{len(mentor.sources)} source(s) loaded. "
            f"{'Every claim is cited.' if mentor.sources else 'It will refuse to answer about him.'}{OFF}"
        )
    print(f"{DIM}Ctrl-C or an empty line to leave.{OFF}\n")
    print(f"{mentor.opening_line}\n")

    persona = mentor_service.persona_prompt(mentor)
    viewer = _viewer(viewer_description)
    turns: list[dict[str, str]] = []

    while True:
        try:
            question = input(f"{BOLD}you ›{OFF} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            return 0

        turns.append({"role": "user", "content": question})
        # Same cap the API enforces, so the terminal behaves like the product.
        turns = turns[-MAX_HISTORY_MESSAGES:]

        print()
        reply = ""
        try:
            async for chunk in llm_service.stream_mentor_reply(persona, viewer, turns):
                reply += chunk
                print(chunk, end="", flush=True)
        except LLMUnavailable as exc:
            print(f"\n{WARN}{exc}{OFF}\n")
            turns.pop()
            continue
        except KeyboardInterrupt:
            print(f"\n{DIM}(stopped){OFF}\n")
            turns.pop()
            continue

        cited, unknown = _citations(reply, mentor)
        if cited:
            print()
            for source in cited:
                url = f" - {source.url}" if source.url else ""
                print(f"{CITE}  [{source.id}]{OFF} {DIM}{source.label}{url}{OFF}")
        if unknown:
            keys = " ".join(f"[{key}]" for key in unknown)
            print(f"{WARN}  unverified: {keys} - no matching source{OFF}")

        print("\n")
        turns.append({"role": "assistant", "content": reply})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mentor", help="Slug. Defaults to the pinned one.")
    parser.add_argument("--as", dest="viewer", help="Who you are, e.g. 'Alice, high school CS'")
    parser.add_argument("--list", action="store_true", help="Show the mentors and exit")
    args = parser.parse_args()

    if args.list:
        for mentor in mentor_service.list_mentors():
            pin = "*" if mentor.pinned else " "
            material = "" if mentor.has_material else "  (no sources loaded)"
            print(f"{pin} {mentor.slug:18} {mentor.mode:13} {mentor.name}{material}")
        return 0

    try:
        return asyncio.run(converse(args.mentor, args.viewer))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
