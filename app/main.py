from fastapi import FastAPI
from app.routers import conjugate, lookup, inflect

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

app.include_router(conjugate.router)
app.include_router(lookup.router)
app.include_router(inflect.router)

@app.get("/health", tags=["System"])
async def health_check():
    """Returns API health status."""
    return {"status": "ok", "version": "0.1.0"}