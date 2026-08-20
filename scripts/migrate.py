#!/usr/bin/env python
"""Apply and record database migrations. See ADR-0023.

    python scripts/migrate.py --status
    python scripts/migrate.py --apply
    python scripts/migrate.py --baseline 003
    python scripts/migrate.py --restamp 003

Uses asyncpg directly rather than SQLAlchemy: migration files contain multiple
statements and DO $$ ... $$ blocks, and asyncpg's prepared-statement path
rejects multi-statement scripts. Connection.execute() with no parameters uses
the simple query protocol, which runs them.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from app import __version__  # noqa: E402
from app.schema_state import MIGRATIONS_DIR, checksum, diff, discover  # noqa: E402

# Read DATABASE_URL directly rather than importing it from app.database: that
# module builds a SQLAlchemy engine as an import-time side effect and raises
# immediately if DATABASE_URL is unset, before this script's own check below
# ever runs. This script doesn't use that engine -- it talks to Postgres via
# asyncpg -- so there's no reason to pull it in.
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    checksum    TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    app_version TEXT
);
"""


def dsn() -> str:
    """asyncpg wants postgresql://; DATABASE_URL is SQLAlchemy's +asyncpg form."""
    if DATABASE_URL is None:
        raise SystemExit("DATABASE_URL is not set")
    return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _confirm(prompt: str) -> bool:
    """input() raises EOFError with a traceback when stdin isn't a TTY (piped
    input, `docker compose run -T`, a wrapper script). Treat that the same as
    a 'no' rather than letting it crash out mid-command."""
    try:
        return input(prompt).strip().lower() == "y"
    except EOFError:
        return False


_DOLLAR_QUOTE_TAG = re.compile(r"\$[A-Za-z_]*\$")
_TXN_CONTROL_LINE = re.compile(
    r"^(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION)\s*;?$", re.IGNORECASE
)


def _strip_transaction_control(sql: str) -> str:
    """Remove top-level BEGIN / COMMIT / ROLLBACK / START TRANSACTION statements.

    cmd_apply wraps every migration in exactly one `async with
    conn.transaction():`. A migration that also opens its own transaction
    (002 has `BEGIN;` ... `COMMIT;`) breaks that promise silently: run
    verbatim inside the runner's transaction, the file's BEGIN is a no-op
    warning and its COMMIT ends the runner's transaction early, so the
    ledger INSERT that follows lands in its own implicit transaction instead
    of the migration's. Nothing raises. Strip the file's own transaction
    control before execution so the runner's transaction is the only one.

    Only a LINE consisting solely of the keyword (optionally followed by
    `;`), with nothing else on it, is stripped -- and only while we are not
    inside a `$tag$ ... $tag$` dollar-quoted block. That second guard is
    what keeps this from corrupting `DO $$ BEGIN ... END $$;` (002 has one):
    the block's own `BEGIN` line would otherwise match the same pattern
    (PL/pgSQL's BEGIN takes no semicolon, same as this bare-line form), but
    because it appears between the block's opening and closing `$$` it is
    left untouched.
    """
    out_lines = []
    in_dollar_quote = None
    for line in sql.split("\n"):
        for tag in _DOLLAR_QUOTE_TAG.findall(line):
            if in_dollar_quote is None:
                in_dollar_quote = tag
            elif tag == in_dollar_quote:
                in_dollar_quote = None
        if in_dollar_quote is None and _TXN_CONTROL_LINE.match(line.strip()):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


async def ensure_ledger(conn) -> None:
    """Create the ledger table. Only the writing commands call this."""
    await conn.execute(LEDGER_DDL)


async def read_ledger(conn) -> dict[str, str]:
    """filename -> checksum. A missing table means an empty ledger, not an error:
    --status must stay genuinely read-only, and an unmigrated database is a
    state to report, not a crash."""
    try:
        rows = await conn.fetch("SELECT filename, checksum FROM schema_migrations")
    except asyncpg.exceptions.UndefinedTableError:
        return {}
    return {r["filename"]: r["checksum"] for r in rows}


async def cmd_status(conn) -> int:
    applied = await read_ledger(conn)
    state = diff(discover(), applied)

    print(f"applied:    {len(applied)}")
    for name in state.pending:
        print(f"  PENDING     {name}")
    for name in state.mismatched:
        print(f"  MISMATCH    {name}  (edited after it was applied)")
    for name in state.ahead:
        print(f"  AHEAD       {name}  (in the database, not in this image)")
    if state.ok and not state.ahead:
        print("  up to date")
    return 0


async def cmd_apply(conn) -> int:
    await ensure_ledger(conn)
    applied = await read_ledger(conn)
    state = diff(discover(), applied)

    if state.mismatched:
        for name in state.mismatched:
            print(f"ERROR: {name} was edited after it was applied.")
        print("Migrations are append-only. Revert the edit, or if the edit was "
              "deliberate, restamp it with --restamp. Refusing to continue.")
        return 1

    if not state.pending:
        print("Nothing to apply.")
        return 0

    for name in state.pending:
        raw = (MIGRATIONS_DIR / name).read_bytes()
        # checksum() always hashes the RAW bytes, unmodified. Only the text
        # handed to conn.execute() below is stripped of the file's own
        # transaction control -- what gets hashed and what gets run are
        # deliberately different things from this point on.
        executable = _strip_transaction_control(raw.decode("utf-8"))
        print(f"applying {name} ...", flush=True)
        # One transaction per migration: a failure at N leaves 1..N-1 recorded
        # and the database consistent, rather than a half-applied batch.
        try:
            async with conn.transaction():
                await conn.execute(executable)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum, app_version) "
                    "VALUES ($1, $2, $3)",
                    name, checksum(raw), __version__,
                )
        except Exception as exc:
            print(f"FAILED on {name}: {exc}")
            print("Earlier migrations remain applied and recorded.")
            return 1
        print(f"  ok  {name}")

    print("Done.")
    return 0


def _prefix(filename: str) -> int:
    """Leading numeric prefix: '002_api_key_hashing.sql' -> 2."""
    return int(filename.split("_", 1)[0])


def _select_upto(upto: int) -> list[tuple[str, str]]:
    files = discover()
    # Compare numerically, not as strings: a string compare of n[:len(upto)]
    # against '3' would stamp '004' too, because '0' < '3'.
    return [(n, c) for n, c in files if _prefix(n) <= upto]


async def cmd_baseline(conn, upto: int) -> int:
    """Stamp migrations as applied without running them, WITHOUT overwriting
    a checksum already recorded (ON CONFLICT ... DO NOTHING). Because of
    that, this cannot repair a MISMATCH -- a row that already exists keeps
    its old checksum. Use --restamp for that."""
    selected = _select_upto(upto)
    if not selected:
        print(f"No migrations at or below {upto}.")
        return 1

    print("Stamping as applied WITHOUT running:")
    for name, _ in selected:
        print(f"  {name}")
    print("\nThis asserts the database ALREADY has these changes.")
    print("Baselining too high silently skips a migration that will never run.")
    if not _confirm("Confirm [y/N]: "):
        print("Aborted.")
        return 1

    await ensure_ledger(conn)
    inserted: list[str] = []
    skipped: list[str] = []
    async with conn.transaction():
        for name, digest in selected:
            # RETURNING is what makes the count honest: a conflicting row
            # under DO NOTHING produces no output row at all, so counting
            # returned rows -- not len(selected) -- is the only way to tell
            # "stamped" from "already there, left untouched".
            row = await conn.fetchrow(
                "INSERT INTO schema_migrations (filename, checksum, app_version) "
                "VALUES ($1, $2, $3) ON CONFLICT (filename) DO NOTHING "
                "RETURNING filename",
                name, digest, __version__,
            )
            (inserted if row is not None else skipped).append(name)

    print(f"Stamped {len(inserted)} migration(s).")
    if skipped:
        print(
            f"{len(skipped)} already recorded, left unchanged (use --restamp "
            "to overwrite a recorded checksum): " + ", ".join(skipped)
        )
    return 0


async def cmd_restamp(conn, upto: int) -> int:
    """Stamp migrations as applied without running them, OVERWRITING any
    checksum already recorded (ON CONFLICT ... DO UPDATE). This is the
    repair OPERATIONS.md and the ADR describe for a MISMATCH: it asserts the
    database already matches the CURRENT contents of the file on disk. It is
    more dangerous than --baseline for exactly that reason -- it can paper
    over a real, unapplied edit just as easily as it can correct the ledger
    after a deliberate one."""
    selected = _select_upto(upto)
    if not selected:
        print(f"No migrations at or below {upto}.")
        return 1

    await ensure_ledger(conn)
    # Read the ledger's current view of these files BEFORE the prompt, so the
    # confirmation can name exactly which recorded checksums are about to be
    # overwritten -- not just which files were selected.
    existing = await conn.fetch(
        "SELECT filename, checksum FROM schema_migrations WHERE filename = ANY($1::text[])",
        [name for name, _ in selected],
    )
    before = {r["filename"]: r["checksum"] for r in existing}
    overwritten = [n for n, c in selected if n in before and before[n] != c]
    fresh = [n for n, _ in selected if n not in before]
    unchanged_names = [n for n, c in selected if n in before and before[n] == c]

    print("Restamping as applied WITHOUT running:")
    for name, _ in selected:
        print(f"  {name}")
    print("\nThis asserts the database ALREADY matches the CURRENT contents of")
    print("these files on disk -- unlike --baseline, it OVERWRITES any checksum")
    print("already recorded for a file, even if that checksum was recorded")
    print("correctly. Only confirm if you have verified the schema actually")
    print("matches; this command cannot check that for you.")
    if overwritten:
        print("\nRecorded checksum WILL BE OVERWRITTEN for:")
        for name in overwritten:
            print(f"  {name}")
    if fresh:
        print("\nNo ledger row yet -- will be inserted fresh for:")
        for name in fresh:
            print(f"  {name}")
    if unchanged_names:
        print("\nAlready matches the recorded checksum, no change for:")
        for name in unchanged_names:
            print(f"  {name}")
    print("\nBaselining too high silently skips a migration that will never run.")
    if not _confirm("Confirm [y/N]: "):
        print("Aborted.")
        return 1

    inserted: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    async with conn.transaction():
        for name, digest in selected:
            row = await conn.fetchrow(
                "INSERT INTO schema_migrations (filename, checksum, app_version) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (filename) DO UPDATE SET "
                "checksum = EXCLUDED.checksum, app_version = EXCLUDED.app_version, "
                "applied_at = NOW() "
                "RETURNING filename",
                name, digest, __version__,
            )
            assert row is not None  # DO UPDATE with no WHERE always affects a row
            if name not in before:
                inserted.append(name)
            elif before[name] != digest:
                updated.append(name)
            else:
                unchanged.append(name)

    print(
        f"Restamped: {len(updated)} checksum(s) overwritten, "
        f"{len(inserted)} newly recorded, {len(unchanged)} already matched."
    )
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description="Apply and record database migrations.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="report state, change nothing")
    g.add_argument("--apply", action="store_true", help="run pending migrations")
    g.add_argument("--baseline", metavar="N", type=int,
                   help="stamp migrations up to prefix N as applied, without running "
                        "them; never overwrites an already-recorded checksum")
    g.add_argument("--restamp", metavar="N", type=int,
                   help="like --baseline, but OVERWRITES the recorded checksum for "
                        "migrations up to prefix N with what is on disk now -- the "
                        "repair for a MISMATCH")
    args = ap.parse_args()

    conn = await asyncpg.connect(dsn())
    try:
        if args.status:
            return await cmd_status(conn)
        if args.apply:
            return await cmd_apply(conn)
        if args.baseline is not None:
            return await cmd_baseline(conn, args.baseline)
        return await cmd_restamp(conn, args.restamp)
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
