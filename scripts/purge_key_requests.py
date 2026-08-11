#!/usr/bin/env python3
"""Purge stale key_requests rows.

Deletes rows that are:
  * expired AND never consumed (dead pending requests), older than a grace window, OR
  * consumed a long time ago (no longer needed — the key lives in api_keys).

Consumed rows are kept briefly for audit/debugging, then removed. Nothing here
touches api_keys — issued keys are permanent until revoked.

Run from cron inside the api container (it has the DB env + deps). Idempotent;
safe to run as often as you like.

Env: DATABASE_URL (or adjust to your app's connection method).
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]

# retention windows
EXPIRED_GRACE = "interval '2 days'"     # keep dead pending rows this long past expiry
CONSUMED_KEEP = "interval '30 days'"    # keep consumed rows this long for audit


async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        res_expired = await conn.execute(text(
            f"DELETE FROM key_requests "
            f"WHERE consumed_at IS NULL AND expires_at < now() - {EXPIRED_GRACE}"
        ))
        res_consumed = await conn.execute(text(
            f"DELETE FROM key_requests "
            f"WHERE consumed_at IS NOT NULL AND consumed_at < now() - {CONSUMED_KEEP}"
        ))
        # rowcount is best-effort across drivers; print for cron logs
        print(f"purged expired-unconsumed: {res_expired.rowcount}, "
              f"old-consumed: {res_consumed.rowcount}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
