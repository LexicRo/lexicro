import os
import secrets
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from sqlalchemy import text
from app.database import AsyncSessionLocal

ANONYMOUS_LIMIT = 10


async def check_rate_limit(request: Request):
    """
    Check API key and rate limit for each request.
    - No key: anonymous quota (10 req/day) tracked by IP
    - Valid key: key's daily_limit applies
    - Invalid key: 401
    """
    api_key = request.headers.get("X-API-Key")
    ip_address = request.client.host
    endpoint = request.url.path

    async with AsyncSessionLocal() as db:
        if api_key:
            # Validate key
            result = await db.execute(
                text("SELECT daily_limit, active FROM api_keys WHERE key = :key"),
                {"key": api_key}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=401, detail="Invalid API key.")
            if not row.active:
                raise HTTPException(status_code=401, detail="API key is inactive.")

            daily_limit = row.daily_limit
            tracker = api_key
            track_field = "api_key"
        else:
            daily_limit = ANONYMOUS_LIMIT
            tracker = ip_address
            track_field = "ip_address"

        # Count today's requests
        today = datetime.now(timezone.utc).date()
        count_result = await db.execute(
            text(f"""
                SELECT COUNT(*) FROM request_log
                WHERE {track_field} = :tracker
                AND requested_at >= :today
            """),
            {"tracker": tracker, "today": today}
        )
        count = count_result.scalar()

        if count >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily rate limit exceeded ({daily_limit} requests/day). "
                       f"{'Provide an API key for a higher limit.' if not api_key else 'Upgrade your plan for a higher limit.'}"
            )

        # Log the request
        await db.execute(
            text("""
                INSERT INTO request_log (api_key, ip_address, endpoint)
                VALUES (:api_key, :ip, :endpoint)
            """),
            {
                "api_key": api_key,
                "ip": ip_address,
                "endpoint": endpoint
            }
        )
        await db.commit()