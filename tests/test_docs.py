"""Contract tests for the documentation pages' head metadata.

These pages are the links the project asks people to check its claims against,
so they get pasted into places that render a preview card from the head: chat
apps, forums, HN comments, social posts. A card is a claim about the page shown
to readers who never open it, and until 2026-09-01 both guide pages shipped
`charset` and `viewport` and nothing else -- no `og:*`, no
`<meta name="description">`. With nothing to read, a scraper invents a
description from page text, and the first text in these pages is the inlined
`<style>` block.

That is not hypothetical: the wrong card was found on 2026-09-01 when
`api.lexicro.com/guide` was pasted into a Facebook post, which is also how the
sibling defect on `/guide/conjugate` and `/attribution` was found -- all three
render through the same `_render()`.

What these tests pin is the presence and per-page distinctness of the tags, not
the wording. The wording is copy and may change; a page silently losing its
description again is the regression worth failing on.
"""

import html as html_lib

import pytest

from app.routers.docs import PAGES, PUBLIC_BASE_URL

# (route, the key in PAGES). The route is also the canonical path in og:url.
ROUTES = [
    ("/guide", "guide"),
    ("/guide/conjugate", "guide/conjugate"),
    ("/attribution", "attribution"),
]


@pytest.fixture(scope="module")
def pages(client):
    """Every documentation page's HTML, fetched once."""
    fetched = {}
    for route, key in ROUTES:
        response = client.get(route)
        assert response.status_code == 200, f"{route} did not render"
        fetched[key] = response.text
    return fetched


@pytest.mark.parametrize("route,key", ROUTES)
def test_page_declares_a_meta_description(pages, route, key):
    """The plain description, which is the fallback every scraper understands."""
    _, _, description = PAGES[key]
    expected = f'<meta name="description" content="{html_lib.escape(description, quote=True)}">'
    assert expected in pages[key], f"{route} is missing its meta description"


@pytest.mark.parametrize("route,key", ROUTES)
def test_page_declares_open_graph_tags(pages, route, key):
    """og:* is what Facebook, LinkedIn, Slack, WhatsApp and Discord read."""
    _, title, description = PAGES[key]
    markup = pages[key]
    for prop, content in (
        ("og:title", title),
        ("og:description", description),
        ("og:url", f"{PUBLIC_BASE_URL}{route}"),
        ("og:type", "website"),
        ("og:site_name", "LexicRo"),
    ):
        expected = (
            f'<meta property="{prop}" '
            f'content="{html_lib.escape(content, quote=True)}">'
        )
        assert expected in markup, f"{route} is missing {prop}"


@pytest.mark.parametrize("route,key", ROUTES)
def test_page_declares_a_twitter_card(pages, route, key):
    """Without this, X renders a bare link rather than the og:* content."""
    assert '<meta name="twitter:card" content="summary">' in pages[key]


def test_every_page_describes_itself_differently(pages):
    """One description reused across three pages is the same defect wearing a tag.

    The pages exist to be told apart -- `/analyze` prose, `/conjugate` prose,
    and licensing -- so three identical cards would be no more useful than the
    invented ones they replace.
    """
    descriptions = [PAGES[key][2] for _, key in ROUTES]
    assert len(set(descriptions)) == len(descriptions), (
        "two documentation pages share a description"
    )
    assert all(d.strip() for d in descriptions), "a page has an empty description"


@pytest.mark.parametrize("route,key", ROUTES)
def test_metadata_is_attribute_escaped(pages, route, key):
    """A raw double quote in copy would end the attribute and break the tag.

    The current strings contain no quotes, so this cannot fail today. It is
    here because the failure mode is invisible on inspection -- the page still
    renders, the card just goes wrong again -- and the copy is expected to be
    edited by someone who will not be thinking about attribute escaping.
    """
    _, title, description = PAGES[key]
    head = pages[key].split("</head>", 1)[0]
    for value in (title, description):
        if '"' in value or "&" in value or "<" in value:
            assert value not in head, (
                f"{route} emits unescaped metadata: {value!r}"
            )
