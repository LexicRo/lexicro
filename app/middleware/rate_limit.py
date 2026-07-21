import os
from datetime import datetime, timezone

from fastapi import Request, HTTPException
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.keys import hash_key, looks_like_key

ANONYMOUS_LIMIT = 10

# Trust proxy headers only when the app is actually behind a reverse proxy.
# If this is on and the app is ever exposed directly, a caller can forge
# X-Forwarded-For and get a fresh anonymous quota per request.
TRUST_PROXY = os.environ.get("TRUST_PROXY", "true").lower() in ("1", "true", "yes")


def client_ip(request: Request) -> str:
    """The caller's address, not the proxy's.

    Behind nginx, request.client.host is the Docker gateway -- the same value
    for every caller -- so anonymous quota tracked on it puts the entire
    internet in one 10/day bucket. Prefer the headers nginx sets.

    Requires nginx to be passing them, e.g.:

        proxy_set_header X-Real-IP       $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    X-Real-IP is preferred: nginx sets it to the immediate peer, so a client
    cannot forge it. X-Forwarded-For is a caller-supplied chain and only its
    rightmost entry is trustworthy -- the leftmost is whatever the client felt
    like sending.
    """
    if TRUST_PROXY:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # rightmost entry was appended by our own proxy
            return forwarded.split(",")[-1].strip()
    return request.client.host


async def check_rate_limit(request: Request):
    """
    Check API key and rate limit for each request.
    - No key: anonymous quota (10 req/day) tracked by IP
    - Valid key: key's daily_limit applies
    - Invalid key: 401

    Keys are stored as SHA-256 digests, never in plaintext, so lookup hashes the
    supplied value and matches on that. Errors quote the key's PREFIX -- the
    first 12 characters, kept in plaintext -- so a user can report a problem by
    pasting the error message, without either party handling a working
    credential. The prefix is echoed only for a key that was FOUND in the
    database; reflecting an unrecognised caller-supplied string back would put
    arbitrary input into error output and logs.
    """
    api_key = request.headers.get("X-API-Key")
    ip_address = client_ip(request)
    endpoint = request.url.path

    async with AsyncSessionLocal() as db:
        key_prefix = None

        if api_key:
            # Shape check first: rejects scanners and typos without a query.
            # Not a security control -- the hash lookup is -- just cheap triage.
            if not looks_like_key(api_key):
                raise HTTPException(status_code=401, detail="Invalid API key.")

            key_hash = hash_key(api_key)
            result = await db.execute(
                text(
                    "SELECT daily_limit, active, revoked_at, key_prefix "
                    "FROM api_keys WHERE key_hash = :key_hash"
                ),
                {"key_hash": key_hash},
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=401, detail="Invalid API key.")
            key_prefix = row.key_prefix
            if row.revoked_at is not None:
                raise HTTPException(
                    status_code=401,
                    detail=f"API key {key_prefix} has been revoked.",
                )
            if not row.active:
                raise HTTPException(
                    status_code=401,
                    detail=f"API key {key_prefix} is inactive.",
                )

            daily_limit = row.daily_limit
            count_sql = (
                "SELECT COUNT(*) FROM request_log "
                "WHERE key_hash = :tracker AND requested_at >= :today"
            )
            tracker = key_hash
        else:
            daily_limit = ANONYMOUS_LIMIT
            key_hash = None
            count_sql = (
                "SELECT COUNT(*) FROM request_log "
                "WHERE ip_address = :tracker AND requested_at >= :today"
            )
            tracker = ip_address

        # Count today's requests.
        # Not atomic with the insert below: two concurrent requests at the limit
        # can both pass. Acceptable at current volume -- the fix is an atomic
        # counter (Redis INCR, or a SELECT ... FOR UPDATE on a counters table),
        # which is worth doing when traffic justifies it, not before.
        today = datetime.now(timezone.utc).date()
        count_result = await db.execute(
            text(count_sql), {"tracker": tracker, "today": today}
        )
        count = count_result.scalar()

        if count >= daily_limit:
            if api_key:
                detail = (
                    f"Daily rate limit exceeded for {key_prefix} "
                    f"({daily_limit} requests/day). Upgrade your plan for a "
                    f"higher limit."
                )
            else:
                detail = (
                    f"Daily rate limit exceeded ({daily_limit} requests/day). "
                    f"Provide an API key for a higher limit."
                )
            raise HTTPException(status_code=429, detail=detail)

        await db.execute(
            text(
                "INSERT INTO request_log (key_hash, ip_address, endpoint) "
                "VALUES (:key_hash, :ip, :endpoint)"
            ),
            {"key_hash": key_hash, "ip": ip_address, "endpoint": endpoint},
        )

        if key_hash is not None:
            # Cheap, and makes `manage_keys.py list` genuinely useful for
            # spotting keys that were issued and never touched.
            await db.execute(
                text("UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = :h"),
                {"h": key_hash},
            )

        await db.commit()
