from fastapi import APIRouter, HTTPException
from app.services.dex_service import lookup_word

router = APIRouter(
    prefix="/lookup",
    tags=["Lexical Lookup"],
)


@router.get("/{word}", summary="Look up a Romanian word in DEXonline")
async def get_lookup(word: str):
    """
    Returns definitions for a Romanian word from main dictionary sources
    (DEX '09, MDA2, DLRLC).

    - Definitions are stripped of HTML formatting
    - Only primary dictionary entries are returned
    - Source and last-modified date are included per definition
    """
    try:
        return await lookup_word(word)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))