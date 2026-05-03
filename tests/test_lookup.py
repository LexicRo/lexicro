import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_lookup_known_word():
    response = client.get("/lookup/casă")
    assert response.status_code == 200
    data = response.json()
    assert data["word"] == "casă"
    assert len(data["definitions"]) > 0
    assert data["definition_count"] == len(data["definitions"])


def test_lookup_has_required_fields():
    response = client.get("/lookup/casă")
    data = response.json()
    first = data["definitions"][0]
    assert "id" in first
    assert "source" in first
    assert "text" in first
    assert "modified" in first


def test_lookup_allowed_sources_only():
    response = client.get("/lookup/casă")
    data = response.json()
    allowed = {"DEX '09", "MDA2", "DLRLC"}
    for defn in data["definitions"]:
        assert defn["source"] in allowed


def test_lookup_no_html_in_text():
    response = client.get("/lookup/casă")
    data = response.json()
    for defn in data["definitions"]:
        assert "<" not in defn["text"]
        assert ">" not in defn["text"]


def test_lookup_verb():
    response = client.get("/lookup/merge")
    assert response.status_code == 200
    data = response.json()
    assert len(data["definitions"]) > 0


def test_lookup_adjective():
    response = client.get("/lookup/frumos")
    assert response.status_code == 200
    data = response.json()
    assert len(data["definitions"]) > 0


def test_lookup_unknown_word():
    response = client.get("/lookup/xyzabc")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()