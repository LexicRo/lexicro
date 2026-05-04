from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.difficulty_service import score_difficulty


class DifficultyRequest(BaseModel):
    text: str


router = APIRouter(
    prefix="/difficulty",
    tags=["Difficulty"],
)


@router.post("/", summary="Estimate CEFR difficulty level for a Romanian word")
async def get_difficulty(request: DifficultyRequest):
    """
    Returns a CEFR level estimate (A1–C2) for a Romanian word using a
    lexical frequency heuristic based on DEXonline source coverage.

    **Confidence levels:**
    - `medium` — found in multiple main dictionary sources
    - `low` — found in secondary sources only
    - `very_low` — found only in specialised sources
    - `none` — word not found; may be misspelled or not Romanian

    **Phase 1 limitation:** heuristic estimate only. Calibrated scoring
    against Romanian B1/B2 exam corpora is planned for Phase 2.
    """
    try:
        return await score_difficulty(request.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))