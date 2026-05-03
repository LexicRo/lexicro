import re
import httpx
import datetime

DEX_URL = "https://dexonline.ro/definitie/{word}/json"
ALLOWED_SOURCES = {"DEX '09", "MDA2", "DLRLC"}


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode common entities."""
    # First pass — remove complete tags
    text = re.sub(r'<[^>]+>', '', html)
    # Second pass — remove any leftover tag fragments from attributes containing >
    text = re.sub(r'[^"]*">', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&#039;', "'").replace('&quot;', '"')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _format_date(timestamp: str) -> str:
    """Convert Unix timestamp string to ISO date."""
    try:
        return datetime.datetime.fromtimestamp(
            int(timestamp), tz=datetime.timezone.utc
        ).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def _extract_headword(html: str) -> str:
    """Extract the headword from the first <b> tag in htmlRep."""
    match = re.search(r'<b[^>]*>(.*?)<\/b>', html)
    if not match:
        return ""
    return _strip_html(match.group(1)).lower().strip('*^1234567890 ,.')


def _headword_matches(html: str, word: str) -> bool:
    """Check that the definition's headword matches the searched word."""
    headword = _extract_headword(html)
    search = word.lower().strip()
    # Allow for diacritics variants and superscript numbers
    return headword.startswith(search[:3]) if len(search) >= 3 else headword == search


async def lookup_word(word: str) -> dict:
    """
    Look up a Romanian word in DEXonline.
    Returns definitions from main dictionary sources only.
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

    filtered = [
        {
            "id": d["id"],
            "source": d["sourceName"],
            "text": _strip_html(d["htmlRep"]),
            "modified": _format_date(d.get("modDate")),
        }
        for d in data["definitions"]
        if d.get("type") == "definition"
           and d.get("sourceName") in ALLOWED_SOURCES
           and d.get("htmlRep")
           and _headword_matches(d["htmlRep"], word)
    ]

    if not filtered:
        raise ValueError(f"No main dictionary definitions found for '{word}'.")

    return {
        "word": data.get("word", word),
        "definitions": filtered,
        "definition_count": len(filtered),
    }