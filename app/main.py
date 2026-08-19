from fastapi import FastAPI, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from app.middleware.rate_limit import check_rate_limit
from app.routers import conjugate, lookup, inflect, difficulty, analyze, docs
from app.routers.keys import router as keys_router   # match your actual path/name
from app import __version__

import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.database import AsyncSessionLocal
from app.schema_state import diff, discover

logger = logging.getLogger("lexicro.schema")

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DESCRIPTION = """
Romanian language APIs - morphological analysis and verb conjugation.

## Authentication

Pass your key in the `X-API-Key` header. Without one you get **10 requests/day**
per IP - enough to try the API, not enough to build on. Get a free key by
[filling in this form](https://tally.so/r/GxBBbz) and confirming your email - it
is issued instantly.

| tier | requests/day |
|---|---|
| anonymous | 10 |
| free (with key) | 1,000 |

## `/analyze`

Returns lemma, part of speech and morphological features for every token **in
context**. A dictionary can tell you *era* is either the imperfect of **a fi**
("to be") or a noun meaning "epoch"; it cannot tell you which one you are
looking at. This endpoint can.

Accuracy on the UD Romanian RRT test split: **98.14%** UPOS, **95.50%** lemma.

[Full documentation](https://api.lexicro.com/guide) | [Attribution](https://api.lexicro.com/attribution)
"""

def verify_schema(applied: dict[str, str]) -> None:
    """Raise if this image's migrations are not all applied to the database.

    Behind or edited -> refuse. Ahead -> serve with a warning: the database
    was migrated by a newer release, and refusing would make rolling the
    application back impossible. See ADR-0023.
    """
    state = diff(discover(), applied)

    for name in state.ahead:
        logger.warning(
            "database has migration %s which this image does not ship "
            "(migrated by a newer release)", name
        )

    if state.ok:
        return

    problems = []
    if state.pending:
        problems.append("not applied: " + ", ".join(state.pending))
    if state.mismatched:
        problems.append("edited after being applied: " + ", ".join(state.mismatched))
    detail = "; ".join(problems)

    logger.error("refusing to serve -- database schema is wrong: %s", detail)
    raise RuntimeError(
        f"database schema is wrong ({detail}). "
        "Run: docker compose run --rm api python scripts/migrate.py --status"
    )


async def _read_ledger() -> dict[str, str]:
    """filename -> checksum. A missing table means an unmigrated database --
    an empty ledger, which verify_schema then reports as "nothing applied"
    rather than dying with a driver error the operator cannot act on."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("SELECT filename, checksum FROM schema_migrations")
            )
        except ProgrammingError:
            return {}
        return {row.filename: row.checksum for row in result}


@asynccontextmanager
async def lifespan(app: FastAPI):
    verify_schema(await _read_ledger())
    yield


app = FastAPI(
    title="LexicRo",
    version=__version__,
    description=DESCRIPTION,
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
    contact={
        "name": "LexicRo",
        "url": "https://lexicro.com",
        "email": "contact@lexicro.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

dependencies = [Depends(api_key_header), Depends(check_rate_limit)]

app.include_router(conjugate.router, dependencies=dependencies)
# Disabled 2026-08-17: /lookup, /inflect and /difficulty proxy dexonline.ro,
# whose terms prohibit automated access without prior written consent.
# Permission requested; do not re-enable without a written yes. See docs ADR.
# app.include_router(lookup.router, dependencies=dependencies)
# app.include_router(inflect.router, dependencies=dependencies)
# app.include_router(difficulty.router, dependencies=dependencies)
app.include_router(analyze.router, dependencies=dependencies)
app.include_router(docs.router)          # public, no dependencies
app.include_router(keys_router)

@app.get("/health", tags=["System"])
async def health_check():
    """Returns API health status."""
    return {"status": "ok", "version": __version__}