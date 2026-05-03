from fastapi import APIRouter, HTTPException
from app.services.verbecc_service import conjugate_verb

router = APIRouter(
    prefix="/conjugate",
    tags=["Conjugation"],
)


@router.get("/{verb}", summary="Conjugate a Romanian verb")
async def get_conjugation(verb: str):
    """
    Returns the full conjugation table for a Romanian verb across all
    moods and tenses.

    - Accepts the verb with or without the Romanian infinitive prefix **a**
      (e.g. both `merge` and `a merge` are valid)
    - Returns conjugation for all moods: indicativ, conjunctiv,
      imperativ, infinitiv, gerunziu, participiu
    """
    try:
        return conjugate_verb(verb)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))