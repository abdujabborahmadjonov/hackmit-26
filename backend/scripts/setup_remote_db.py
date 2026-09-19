#!/usr/bin/env python
"""One-command bootstrap for a hosted database (Supabase, Neon, Render, ...).

    python scripts/setup_remote_db.py

Prompts for the connection string (input is hidden), then:

    1. connects and checks the server
    2. enables the pgvector + pg_trgm extensions
    3. writes DATABASE_URL into .env
    4. runs the migrations
    5. seeds demo data
    6. verifies the recommendation engine on the real database

Pass --url to skip the prompt, --skip-seed to leave existing data alone.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import normalise_database_url  # noqa: E402

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)


# flush=True everywhere: this script interleaves its own output with that of
# subprocesses, and a block-buffered pipe would reorder the two.
def step(number: int, text: str) -> None:
    print(f"\n{BOLD}[{number}/6] {text}{RESET}", flush=True)


def ok(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}", flush=True)


def warn(text: str) -> None:
    print(f"  {YELLOW}!{RESET} {text}", flush=True)


def fail(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}", flush=True)


def redact(url: str) -> str:
    """Never print a password, not even into a scrollback buffer."""
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:••••••@", url)


PLACEHOLDERS = ("[YOUR-PASSWORD]", "YOUR-PASSWORD", "[PASSWORD]", "password")

# scheme://user:password@host... - password is everything up to the LAST '@',
# because a password may legitimately contain one.
_URL_RE = re.compile(r"^(?P<scheme>[a-z+]+)://(?P<user>[^:/@]+):(?P<password>.*)@(?P<rest>.+)$")


def fix_password(url: str) -> str:
    """Percent-encode the password, prompting for it if it is still a placeholder.

    Supabase passwords routinely contain @ # ? / & - characters that silently
    corrupt a URL. Encoding here means the user never has to think about it.
    """
    match = _URL_RE.match(url)
    if not match:
        return url
    password = match.group("password")

    if password in PLACEHOLDERS or not password:
        print(
            f"\n  {YELLOW}!{RESET} The string still has the placeholder password in it."
            f"\n    {DIM}Supabase -> Connect -> Reset database password, then paste it here.{RESET}"
        )
        password = getpass.getpass("  Database password: ").strip()
        if not password:
            return url

    encoded = quote(password, safe="")
    if encoded != password:
        ok("Password contained special characters - percent-encoded for the URL")
    return (
        f"{match.group('scheme')}://{match.group('user')}:{encoded}@{match.group('rest')}"
    )


def libpq_dsn(url: str) -> str:
    """asyncpg.connect() wants the plain libpq form."""
    return url.replace("+asyncpg", "", 1)


def check_host(url: str) -> None:
    """Catch the two connection strings that cannot work before we try them."""
    match = re.search(r"@([^:/?]+)", url)
    host = match.group(1) if match else ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        warn(
            "That is Supabase's DIRECT connection, which is IPv6-only.\n"
            "    It works from your laptop but NOT from Render (IPv4 only).\n"
            "    Use Connect -> Session pooler instead (*.pooler.supabase.com)."
        )
    if ":6543" in url:
        warn(
            "Port 6543 is the TRANSACTION pooler. Set\n"
            "    DB_DISABLE_PREPARED_STATEMENTS=true in .env, or use port 5432."
        )


async def prepare(url: str) -> bool:
    import asyncpg

    step(1, "Connecting")
    print(f"  {DIM}{redact(url)}{RESET}")
    try:
        conn = await asyncpg.connect(libpq_dsn(url), timeout=20)
    except Exception as exc:
        fail(f"Could not connect: {type(exc).__name__}: {exc}")
        if "password authentication failed" in str(exc):
            print(
                f"\n  {DIM}The host and user are right, so this is the password itself.\n"
                "  It is the DATABASE password, not your Supabase account password.\n"
                "  Get a fresh one: Connect -> Reset database password, copy it,\n"
                f"  and run this script again.{RESET}"
            )
        else:
            print(
                f"\n  {DIM}Common causes: the direct (IPv6) host instead of the pooler,\n"
                f"  a missing ?sslmode=require, or a firewall.{RESET}"
            )
        return False

    try:
        version = await conn.fetchval("SELECT version()")
        ok(version.split(",")[0])

        step(2, "Enabling extensions")
        for extension in ("vector", "pg_trgm"):
            try:
                await conn.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
                installed = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = $1", extension
                )
                ok(f"{extension} {installed}")
            except Exception as exc:
                fail(f"{extension}: {exc}")
                print(
                    f"\n  {DIM}Enable it once in the Supabase SQL editor:\n"
                    f"    create extension if not exists {extension};{RESET}"
                )
                return False

        # pgvector installed outside the default search_path breaks the migration.
        schema = await conn.fetchval(
            "SELECT n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        )
        if schema not in ("public", None):
            search_path = await conn.fetchval("SHOW search_path")
            if schema not in search_path:
                warn(f"pgvector lives in schema '{schema}', which is not on the search_path.")
                print(
                    f"  {DIM}Run once in the SQL editor:\n"
                    f"    alter database postgres set search_path to public, {schema};{RESET}"
                )
    finally:
        await conn.close()
    return True


def write_env(url: str) -> None:
    step(3, "Writing .env")
    env_path = BACKEND / ".env"
    line = f"DATABASE_URL={normalise_database_url(url)}"
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        replaced = False
        for index, existing in enumerate(lines):
            if existing.startswith("DATABASE_URL="):
                lines[index] = line
                replaced = True
                break
        if not replaced:
            lines.append(line)
    else:
        lines = [line]
    env_path.write_text("\n".join(lines) + "\n")
    ok(f"{env_path.name} updated (gitignored, never committed)")


def run(command: list[str], label: str, echo: bool = True) -> bool:
    if echo:
        print(f"  {DIM}$ {' '.join(command)}{RESET}", flush=True)
    sys.stdout.flush()
    result = subprocess.run(command, cwd=BACKEND)
    if result.returncode != 0:
        fail(f"{label} failed with exit code {result.returncode}")
        return False
    ok(f"{label} complete")
    return True


async def verify(scale: float) -> bool:
    step(6, "Verifying the recommendation engine")
    from sqlalchemy import func, select

    from app.database import SessionLocal, engine
    from app.models.profile import TeacherProfile
    from app.models.resource import Resource
    from app.models.user import User
    from app.services.recommendation_service import RecommendationService

    async with SessionLocal() as session:
        teachers = await session.scalar(select(func.count()).select_from(TeacherProfile))
        resources = await session.scalar(select(func.count()).select_from(Resource))
        ok(f"{teachers:,} teacher profiles, {resources:,} resources")

        alice = await session.scalar(
            select(User).where(User.email == "demo_teacher@example.com")
        )
        if alice is None:
            warn("Demo accounts not present - seeding was skipped?")
            await engine.dispose()
            return True

        started = time.perf_counter()
        result = await RecommendationService(session).recommend(alice.id, limit=5)
        elapsed = (time.perf_counter() - started) * 1000

        names = [item.user.first_name for item in result.items]
        ok(f"GET /recommendations equivalent: {elapsed:.0f} ms over the network")
        for item in result.items[:3]:
            print(
                f"      {item.breakdown.total:.3f}  {item.user.first_name} "
                f"{item.user.last_name}  {DIM}{item.reasons[0] if item.reasons else ''}{RESET}"
            )
        if names and names[0] == "Bob":
            ok("Alice's top match is Bob - the demo scenario works on this database")
        else:
            warn(f"Expected Bob first, got {names[:3]}")
    await engine.dispose()
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a hosted database")
    parser.add_argument("--url", help="Connection string (otherwise prompted for)")
    parser.add_argument("--scale", type=float, default=0.1, help="Demo data size (default 0.1)")
    parser.add_argument("--skip-seed", action="store_true")
    # Verification runs in a fresh interpreter: settings are read once at
    # import, so it has to start after .env has been rewritten.
    parser.add_argument("--verify-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.verify_only:
        await verify(args.scale)
        return 0

    print(f"{BOLD}EduMatch - hosted database setup{RESET}")
    url = args.url
    if not url:
        print(
            "\nPaste your connection string. Supabase: Connect -> Session pooler.\n"
            f"{DIM}Input is hidden and the password is never printed or logged.{RESET}"
        )
        url = getpass.getpass("DATABASE_URL: ").strip()
    if not url:
        fail("No connection string given.")
        return 1
    if not url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
        fail("That does not look like a Postgres URL. It should start with postgresql://")
        return 1

    url = fix_password(url)
    check_host(url)
    if not await prepare(url):
        return 1

    write_env(url)
    os.environ["DATABASE_URL"] = normalise_database_url(url)

    python = sys.executable
    step(4, "Running migrations")
    if not run([python, "-m", "alembic", "upgrade", "head"], "Migrations"):
        return 1

    step(5, "Seeding demo data")
    if args.skip_seed:
        print(f"  {DIM}skipped (--skip-seed){RESET}")
    elif not run(
        [python, "scripts/generate_demo_data.py", "--scale", str(args.scale)], "Demo data"
    ):
        return 1

    run([python, "scripts/setup_remote_db.py", "--verify-only"], "Verification", echo=False)

    print(f"\n{GREEN}{BOLD}Database is ready.{RESET}")
    print(
        "\nNext: Render -> New -> Blueprint -> this repo, branch 'backend'.\n"
        "Paste the SAME connection string as DATABASE_URL, plus SUPABASE_URL and\n"
        "SUPABASE_SERVICE_KEY (Project Settings -> API) when Render asks.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
