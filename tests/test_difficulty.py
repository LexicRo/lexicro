import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_difficulty_known_word():
    response = client.post("/difficulty/", json={"text": "casă"})
    assert response.status_code == 200
    data = response.json()
    assert data["valid_romanian_word"] is True
    assert data["cefr_level"] is None
    assert data["method"] == "dictionary_validation"


def test_difficulty_unknown_word():
    response = client.post("/difficulty/", json={"text": "xyzabc"})
    assert response.status_code == 200
    data = response.json()
    assert data["valid_romanian_word"] is False
    assert data["cefr_level"] is None


def test_difficulty_has_required_fields():
    response = client.post("/difficulty/", json={"text": "casă"})
    data = response.json()
    assert "text" in data
    assert "valid_romanian_word" in data
    assert "cefr_level" in data
    assert "confidence" in data
    assert "method" in data
    assert "explanation" in data
    assert "note" in data


def test_difficulty_note_mentions_phase2():
    response = client.post("/difficulty/", json={"text": "casă"})
    data = response.json()
    assert "Phase 2" in data["note"]


def test_difficulty_empty_text():
    response = client.post("/difficulty/", json={"text": ""})
    assert response.status_code == 400


def test_difficulty_technical_word():
    response = client.post("/difficulty/", json={"text": "hipostază"})
    assert response.status_code == 200
    data = response.json()
    assert "valid_romanian_word" in data