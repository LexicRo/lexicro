from fastapi import FastAPI, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from app.middleware.rate_limit import check_rate_limit
from app.routers import conjugate, lookup, inflect, difficulty, analyze, docs
from app import __version__

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DESCRIPTION = """
Romanian language APIs — morphological analysis, conjugation, inflection and
lexical lookup.

## Authentication

Pass your key in the `X-API-Key` header. Without one you get **10 requests/day**
per IP — enough to try the API, not enough to build on. Keys are issued on request — [request one here](https://tally.so/r/GxBBbz)
or email **contact@lexicro.com**.

| tier | requests/day |
|---|---|
| anonymous | 10 |
| free (with key) | 1,000 |

## `/analyze`

Returns lemma, part of speech and morphological features for every token **in
context**. A dictionary can tell you *era* is either the imperfect of **a fi**
or the definite singular of **eră**; it cannot tell you which one you are
looking at. This endpoint can.

Accuracy on the UD Romanian RRT test split: **98.14%** UPOS, **95.50%** lemma.

📖 [Full documentation](https://api.lexicro.com/guide) ·
📄 [Attribution](https://api.lexicro.com/attribution)
"""

app = FastAPI(
    title="LexicRo",
    version=__version__,
    description=DESCRIPTION,
    default_response_class=UTF8JSONResponse,
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
app.include_router(lookup.router, dependencies=dependencies)
app.include_router(inflect.router, dependencies=dependencies)
app.include_router(difficulty.router, dependencies=dependencies)
app.include_router(analyze.router, dependencies=dependencies)
app.include_router(docs.router)          # public, no dependencies

@app.get("/health", tags=["System"])
async def health_check():
    """Returns API health status."""
    return {"status": "ok", "version": __version__}