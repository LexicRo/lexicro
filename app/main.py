from fastapi import FastAPI, Depends
from fastapi.security import APIKeyHeader
from app.routers import conjugate, lookup, inflect, difficulty
from app.middleware.rate_limit import check_rate_limit
from app.routers import conjugate, lookup, inflect, difficulty, analyze

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title="LexicRo API",
    description="Romanian Language Intelligence Infrastructure — morphological analysis, conjugation, and lexical lookup.",
    version="0.1.0",
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

@app.get("/health", tags=["System"])
async def health_check():
    """Returns API health status."""
    return {"status": "ok", "version": "0.1.0"}