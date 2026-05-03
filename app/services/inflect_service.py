import re
import httpx

DEX_URL = "https://dexonline.ro/definitie/{word}/json"
ALLOWED_SOURCES = {"DEX '09", "MDA2", "DLRLC"}


def _extract_forms(html: str) -> str | None:
    """
    Extract inflected forms from the italic text immediately
    after the headword bold tag.
    e.g. <b>CASĂ...</b> <i>case,</i> → "case"
    """
    match = re.search(r'</b>\s*<i>(.*?)</i>', html)
    if not match:
        return None
    # Strip any nested tags and clean up
    text = re.sub(r'<[^>]+>', '', match.group(1))
    return text.strip().rstrip(',').strip()


def _extract_grammar(html: str) -> str | None:
    """
    Extract grammatical category from the first <abbr> data-bs-content
    attribute after the headword.
    e.g. data-bs-content="substantiv feminin" → "substantiv feminin"
    """
    match = re.search(r'data-bs-content="([^"]+)"', html)
    if not match:
        return None
    return match.group(1).strip()


async def inflect_word(word: str) -> dict:
    """
    Extract basic inflection info for a Romanian word from DEXonline.
    Returns plural/comparative forms and grammatical category.
    Raises ValueError if the word is not found.
    """
    url = DEX_URL.format(word=word)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)

    if response.status_code != 200:
        raise ValueError(f"Word '{word}' not found in DEXonline.")

    data = response.json()

    if not data.get("definitions"):
        raise ValueError(f"No definitions found for '{word}'.")

    # Find the first matching definition from allowed sources
    definition = next(
        (
            d for d in data["definitions"]
            if d.get("type") == "definition"
            and d.get("sourceName") in ALLOWED_SOURCES
            and d.get("htmlRep")
        ),
        None
    )

    if not definition:
        raise ValueError(f"No main dictionary entry found for '{word}'.")

    html = definition["htmlRep"]
    forms = _extract_forms(html)
    grammar = _extract_grammar(html)

    return {
        "word": data.get("word", word),
        "word_type": grammar,
        "forms": forms,
        "source": definition["sourceName"],
        "note": "Basic inflection extracted from dictionary header. Full paradigm tables (all cases) available in Phase 2."
    }