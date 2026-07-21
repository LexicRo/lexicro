#!/usr/bin/env python3
"""Issue, list and revoke API keys.

Run it inside the api container so it picks up DATABASE_URL:

    docker-compose exec api python scripts/manage_keys.py issue \
        --email someone@example.com --label "Early access" --tier free

    docker-compose exec api python scripts/manage_keys.py list
    docker-compose exec api python scripts/manage_keys.py revoke --prefix lxr_kJ8mN2pQ

Manual issuance is deliberate for now. It is a real signup path, it takes an
hour rather than a week, and it puts you in direct contact with the first
people using the API -- which is worth more at this stage than automation.
Self-serve can follow once there is demand to justify it.

The key is printed ONCE. It is not recoverable afterwards, by design.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.keys import generate_key, hash_key  # noqa: E402


def dsn() -> str:
    """asyncpg wants a plain postgres:// URL, not SQLAlchemy's dialect form."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def issue(args) -> None:
    key = generate_key()
    conn = await asyncpg.connect(dsn())
    try:
        await conn.execute(
            """
            INSERT INTO api_keys (key_hash, key_prefix, email, label, tier, daily_limit)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            key.key_hash, key.key_prefix, args.email, args.label,
            args.tier, args.daily_limit,
        )
    finally:
        await conn.close()

    print()
    print("  API key issued -- this is the ONLY time it will be shown")
    print()
    print(f"    {key.secret}")
    print()
    print(f"    prefix : {key.key_prefix}")
    print(f"    email  : {args.email}")
    print(f"    tier   : {args.tier}   limit: {args.daily_limit}/day")
    print()
    print("  Send it over a channel the recipient controls, and do not paste it")
    print("  into a ticket or a chat log you do not own.")
    print()


async def list_keys(args) -> None:
    conn = await asyncpg.connect(dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT key_prefix, email, label, tier, daily_limit, active,
                   created_at, last_used_at, revoked_at
              FROM api_keys
             ORDER BY created_at DESC
            """
        )
    finally:
        await conn.close()

    if not rows:
        print("no keys issued")
        return

    print(f"{'prefix':<14}{'tier':<8}{'limit':>7}  {'state':<9}"
          f"{'last used':<12}{'email'}")
    print("-" * 78)
    for r in rows:
        if r["revoked_at"]:
            state = "revoked"
        elif not r["active"]:
            state = "inactive"
        else:
            state = "active"
        last = r["last_used_at"].date().isoformat() if r["last_used_at"] else "never"
        print(f"{r['key_prefix']:<14}{r['tier']:<8}{r['daily_limit']:>7}  "
              f"{state:<9}{last:<12}{r['email'] or ''}")


async def revoke(args) -> None:
    conn = await asyncpg.connect(dsn())
    try:
        # Revoke by prefix: the full key is unrecoverable, which is the point.
        result = await conn.execute(
            """
            UPDATE api_keys
               SET active = FALSE, revoked_at = NOW()
             WHERE key_prefix = $1 AND revoked_at IS NULL
            """,
            args.prefix,
        )
    finally:
        await conn.close()
    n = int(result.split()[-1])
    print(f"revoked {n} key(s) with prefix {args.prefix}"
          if n else f"no active key with prefix {args.prefix}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("issue", help="mint a new key")
    p.add_argument("--email", required=True)
    p.add_argument("--label", default=None, help="what this key is for")
    p.add_argument("--tier", default="free")
    p.add_argument("--daily-limit", type=int, default=1000)
    p.set_defaults(fn=issue)

    p = sub.add_parser("list", help="list issued keys (never shows secrets)")
    p.set_defaults(fn=list_keys)

    p = sub.add_parser("revoke", help="revoke a key by its prefix")
    p.add_argument("--prefix", required=True)
    p.set_defaults(fn=revoke)

    args = ap.parse_args()
    asyncio.run(args.fn(args))


if __name__ == "__main__":
    main()
