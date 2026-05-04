import httpx

DEX_URL = "https://dexonline.ro/definitie/{word}/json"

MAIN_SOURCES = {"DEX '09", "MDA2", "DLRLC"}

NOTE_PHASE2 = (
    "Phase 1: word validation only — confirms whether the word exists in "
    "standard Romanian dictionaries. CEFR level scoring against Romanian "
    "B1/B2 exam corpora is planned for Phase 2."
)


async def score_difficulty(text: str) -> dict:
    """
    Validate whether a Romanian word exists in standard dictionaries.
    Full CEFR scoring is planned for Phase 2.
    """
    word = text.strip().lower()

    if not word:
        raise ValueError("Text cannot be empty.")

    url = DEX_URL.format(word=word)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)

    if response.status_code != 200:
        return {
            "text": text,
            "valid_romanian_word": False,
            "cefr_level": None,
            "confidence": "none",
            "method": "dictionary_validation",
            "explanation": "Word not found in DEXonline. May be misspelled, a proper noun, or not a Romanian word.",
            "note": NOTE_PHASE2
        }

    data = response.json()
    definitions = data.get("definitions", [])

    in_main = any(
        d.get("type") == "definition" and d.get("sourceName") in MAIN_SOURCES
        for d in definitions
    )

    if in_main:
        return {
            "text": text,
            "valid_romanian_word": True,
            "cefr_level": None,
            "confidence": "none",
            "method": "dictionary_validation",
            "explanation": "Word found in standard Romanian dictionaries (DEX '09, MDA2, or DLRLC).",
            "note": NOTE_PHASE2
        }
    else:
        return {
            "text": text,
            "valid_romanian_word": False,
            "cefr_level": None,
            "confidence": "none",
            "method": "dictionary_validation",
            "explanation": "Word not found in main dictionary sources. May be specialised, archaic, misspelled, or not a Romanian word.",
            "note": NOTE_PHASE2
        }