from fastapi import APIRouter, HTTPException
from app.services.inflect_service import inflect_word

router = APIRouter(
    prefix="/inflect",
    tags=["Inflection"],
)


@router.get("/{word}", summary="Get inflection info for a Romanian word")
async def get_inflection(word: str):
    """
    Returns basic inflection information for a Romanian word —
    plural forms for nouns, comparative/feminine forms for adjectives.

    **Phase 1 limitation:** forms are extracted from dictionary headers
    and cover the most common inflected forms only. Full paradigm tables
    (all cases, numbers, genders) are planned for Phase 2.
    """
    try:
        return await inflect_word(word)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))