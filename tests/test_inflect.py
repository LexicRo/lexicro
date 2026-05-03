import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_inflect_noun():
    response = client.get("/inflect/casă")
    assert response.status_code == 200
    data = response.json()
    assert data["word"] == "casă"
    assert data["word_type"] == "substantiv feminin"
    assert "case" in data["forms"]
    assert data["source"] == "DEX '09"


def test_inflect_adjective():
    response = client.get("/inflect/frumos")
    assert response.status_code == 200
    data = response.json()
    assert data["word_type"] == "adjectiv"
    assert "frumoși" in data["forms"]


def test_inflect_verb():
    response = client.get("/inflect/merge")
    assert response.status_code == 200
    data = response.json()
    assert data["word_type"] == "verb"
    assert data["forms"] is not None


def test_inflect_has_required_fields():
    response = client.get("/inflect/casă")
    data = response.json()
    assert "word" in data
    assert "word_type" in data
    assert "forms" in data
    assert "source" in data
    assert "note" in data


def test_inflect_note_mentions_phase2():
    response = client.get("/inflect/casă")
    data = response.json()
    assert "Phase 2" in data["note"]


def test_inflect_unknown_word():
    response = client.get("/inflect/xyzabc")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()