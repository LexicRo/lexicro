import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Endpoint withdrawn from the product surface (ADR-0025); its router is "
        "commented out in app/main.py. Tests are kept, not deleted: the "
        "endpoints may return, and a deleted test is a lost specification."
    )
)


def test_lookup_known_word(client):
    response = client.get("/lookup/casă")
    assert response.status_code == 200
    data = response.json()
    assert data["word"] == "casă"
    assert len(data["definitions"]) > 0
    assert data["definition_count"] == len(data["definitions"])


def test_lookup_has_required_fields(client):
    response = client.get("/lookup/casă")
    data = response.json()
    first = data["definitions"][0]
    assert "id" in first
    assert "source" in first
    assert "text" in first
    assert "modified" in first


def test_lookup_allowed_sources_only(client):
    response = client.get("/lookup/casă")
    data = response.json()
    allowed = {"DEX '09", "MDA2", "DLRLC"}
    for defn in data["definitions"]:
        assert defn["source"] in allowed


def test_lookup_no_html_in_text(client):
    response = client.get("/lookup/casă")
    data = response.json()
    for defn in data["definitions"]:
        assert "<" not in defn["text"]
        assert ">" not in defn["text"]


def test_lookup_verb(client):
    response = client.get("/lookup/merge")
    assert response.status_code == 200
    data = response.json()
    assert len(data["definitions"]) > 0


def test_lookup_adjective(client):
    response = client.get("/lookup/frumos")
    assert response.status_code == 200
    data = response.json()
    assert len(data["definitions"]) > 0


def test_lookup_unknown_word(client):
    response = client.get("/lookup/xyzabc")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
