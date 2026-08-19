#!/usr/bin/env python
"""Apply and record database migrations. See ADR-0023.

    python scripts/migrate.py --status
    python scripts/migrate.py --apply
    python scripts/migrate.py --baseline 003

Uses asyncpg directly rather than SQLAlchemy: migration files contain multiple
statements and DO $$ ... $$ blocks, and asyncpg's prepared-statement path
rejects multi-statement scripts. Connection.execute() with no parameters uses
the simple query protocol, which runs them.
"""

from __future__ import annotations

import argparse
import asyncio
import os
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
        print("Migrations are append-only. Revert the edit, or re-baseline "
              "deliberately. Refusing to continue.")
        return 1

    if not state.pending:
        print("Nothing to apply.")
        return 0

    for name in state.pending:
        raw = (MIGRATIONS_DIR / name).read_bytes()
        print(f"applying {name} ...", flush=True)
        # One transaction per migration: a failure at N leaves 1..N-1 recorded
        # and the database consistent, rather than a half-applied batch.
        try:
            async with conn.transaction():
                await conn.execute(raw.decode("utf-8"))
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


async def cmd_baseline(conn, upto: str) -> int:
    files = discover()
    # Compare numerically, not as strings: a string compare of n[:len(upto)]
    # against '3' would stamp '004' too, because '0' < '3'.
    selected = [(n, c) for n, c in files if _prefix(n) <= int(upto)]
    if not selected:
        print(f"No migrations at or below {upto}.")
        return 1

    print("Stamping as applied WITHOUT running:")
    for name, _ in selected:
        print(f"  {name}")
    print("\nThis asserts the database ALREADY has these changes.")
    print("Baselining too high silently skips a migration that will never run.")
    if input("Confirm [y/N]: ").strip().lower() != "y":
        print("Aborted.")
        return 1

    await ensure_ledger(conn)
    async with conn.transaction():
        for name, digest in selected:
            await conn.execute(
                "INSERT INTO schema_migrations (filename, checksum, app_version) "
                "VALUES ($1, $2, $3) ON CONFLICT (filename) DO NOTHING",
                name, digest, __version__,
            )
    print(f"Stamped {len(selected)} migration(s).")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description="Apply and record database migrations.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="report state, change nothing")
    g.add_argument("--apply", action="store_true", help="run pending migrations")
    g.add_argument("--baseline", metavar="N",
                   help="stamp migrations up to prefix N as applied, without running them")
    args = ap.parse_args()

    conn = await asyncpg.connect(dsn())
    try:
        if args.status:
            return await cmd_status(conn)
        if args.apply:
            return await cmd_apply(conn)
        return await cmd_baseline(conn, args.baseline)
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
