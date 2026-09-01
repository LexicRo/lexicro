"""Human-readable documentation, rendered from the markdown in `docs/`.

The site (lexicro.com, cPanel/Apache) and the API (Hetzner) are different
machines, so a docs page on the site would be a hand-maintained second copy of
these files -- and second copies drift. Serving them from the API instead keeps
`docs/analyze.md` the single source: edit it, redeploy, both surfaces update.
The site just links here.

Routes:
    /guide             -> the /analyze guide      (docs/analyze.md)
    /guide/conjugate   -> the /conjugate guide     (docs/conjugate.md)
    /attribution       -> licensing and credits    (ATTRIBUTION.md)

Deliberately NOT under /docs, which FastAPI uses for the interactive Swagger UI.
Two different things: /docs is the API explorer, /guide is prose.

These routes are public -- no API key, and excluded from rate limiting.
Documentation that requires a key to read is documentation nobody reads.
"""

from __future__ import annotations

import html as html_lib
import os
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Documentation"], include_in_schema=False)

# Repo root: app/routers/docs.py -> app/routers -> app -> /app
ROOT = Path(__file__).resolve().parent.parent.parent

# Same env var and same default as the signup flow in routers/keys.py, so a
# deployment that moves the API moves its canonical URLs with it.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://api.lexicro.com")

# (source file, <title>, description).
#
# The description is not decoration. These pages are what the project asks
# people to check its claims against, so they get pasted into chat apps, forums
# and social posts, all of which render a preview card from the head. Until
# 2026-09-01 these pages carried `charset` and `viewport` and nothing else, so
# scrapers invented a description from page text -- and the first text here is
# the inlined <style> block. That produced a visibly wrong card the first time
# `/guide` was shared. Keep each one short, true, and about *this* page.
PAGES = {
    "guide": (
        ROOT / "docs" / "analyze.md",
        "LexicRo — /analyze guide",
        "How /analyze works: for every token, its lemma, part of speech and "
        "morphological features — and which component produced each one.",
    ),
    "guide/conjugate": (
        ROOT / "docs" / "conjugate.md",
        "LexicRo — /conjugate guide",
        "How /conjugate works: Romanian conjugation tables across seven moods, "
        "with the source of every form.",
    ),
    "attribution": (
        ROOT / "ATTRIBUTION.md",
        "LexicRo — Attribution",
        "Licences and credits for the data, models and libraries behind LexicRo.",
    ),
}

# Minimal, readable, no external requests. A docs page that pulls in a CDN
# stylesheet breaks the moment the CDN does.
STYLE = """
:root { color-scheme: light dark; }
body {
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        Helvetica, Arial, sans-serif;
  max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 6rem;
  color: #1a1a1a; background: #fff;
}
@media (prefers-color-scheme: dark) {
  body { color: #e4e4e4; background: #16171a; }
  a { color: #7cb7ff; }
  code, pre { background: #23252a !important; }
  th { background: #23252a !important; }
  td, th { border-color: #34363c !important; }
  hr { border-color: #34363c !important; }
}
h1 { font-size: 1.9rem; margin-top: 0; }
h2 { font-size: 1.35rem; margin-top: 2.5rem;
     padding-bottom: .3rem; border-bottom: 1px solid #e3e3e3; }
h3 { font-size: 1.1rem; margin-top: 2rem; }
a { color: #0b62d0; }
code { background: #f4f4f6; padding: .15em .4em; border-radius: 3px;
       font-size: .875em; }
pre { background: #f4f4f6; padding: 1rem; border-radius: 6px;
      overflow-x: auto; }
pre code { background: none; padding: 0; font-size: .85em; }
table { border-collapse: collapse; width: 100%; margin: 1.25rem 0;
        font-size: .93em; }
th, td { border: 1px solid #ddd; padding: .5rem .7rem; text-align: left; }
th { background: #f7f7f8; }
blockquote { margin: 1.25rem 0; padding: .1rem 1rem; border-left: 3px solid #ccc;
             color: #555; }
@media (prefers-color-scheme: dark) { blockquote { color: #aaa; } }
hr { border: 0; border-top: 1px solid #e3e3e3; margin: 2.5rem 0; }
.nav { font-size: .9rem; margin-bottom: 2rem; }
.nav a { margin-right: 1rem; }
"""

NAV = (
    '<div class="nav">'
    '<a href="/guide">/analyze</a>'
    '<a href="/guide/conjugate">/conjugate</a>'
    '<a href="/docs">API explorer</a>'
    '<a href="/attribution">Attribution</a>'
    '<a href="https://lexicro.com">lexicro.com</a>'
    "</div>"
)


def _meta(title: str, description: str, route: str) -> str:
    """The head metadata a link preview is built from.

    Escaped with quote=True because these values land inside double-quoted
    attributes: a raw `"` in the copy would close the attribute early and the
    tag would go wrong silently -- the page still renders, only the card breaks,
    which is precisely the failure that is hard to notice.

    No og:image: there is no card image to point at yet, and a tag pointing at
    a missing one is worse than its absence. Scrapers fall back to a text card.
    """
    esc = lambda value: html_lib.escape(value, quote=True)  # noqa: E731
    return (
        f'<meta name="description" content="{esc(description)}">'
        f'<meta property="og:title" content="{esc(title)}">'
        f'<meta property="og:description" content="{esc(description)}">'
        f'<meta property="og:url" content="{esc(PUBLIC_BASE_URL + route)}">'
        f'<meta property="og:type" content="website">'
        f'<meta property="og:site_name" content="LexicRo">'
        f'<meta name="twitter:card" content="summary">'
    )


def _render(path: Path, title: str, description: str, route: str) -> str:
    if not path.exists():
        raise HTTPException(status_code=404, detail="Documentation not found.")
    html = markdown.markdown(
        path.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc"],
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html_lib.escape(title)}</title>"
        f"{_meta(title, description, route)}"
        f"<style>{STYLE}</style></head>"
        f"<body>{NAV}{html}</body></html>"
    )


def _page(key: str) -> str:
    """Render the page registered under `key`, whose route is `/{key}`."""
    path, title, description = PAGES[key]
    return _render(path, title, description, f"/{key}")


@router.get("/guide", response_class=HTMLResponse)
def guide() -> str:
    return _page("guide")


@router.get("/guide/conjugate", response_class=HTMLResponse)
def guide_conjugate() -> str:
    return _page("guide/conjugate")


@router.get("/attribution", response_class=HTMLResponse)
def attribution() -> str:
    return _page("attribution")
