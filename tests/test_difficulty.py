import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Endpoint withdrawn from the product surface (ADR-0025); its router is "
        "commented out in app/main.py. Tests are kept, not deleted: the "
        "endpoints may return, and a deleted test is a lost specification."
    )
)


def test_difficulty_known_word(client):
    response = client.post("/difficulty/", json={"text": "casă"})
    assert response.status_code == 200
    data = response.json()
    assert data["valid_romanian_word"] is True
    assert data["cefr_level"] is None
    assert data["method"] == "dictionary_validation"


def test_difficulty_unknown_word(client):
    response = client.post("/difficulty/", json={"text": "xyzabc"})
    assert response.status_code == 200
    data = response.json()
    assert data["valid_romanian_word"] is False
    assert data["cefr_level"] is None


def test_difficulty_has_required_fields(client):
    response = client.post("/difficulty/", json={"text": "casă"})
    data = response.json()
    assert "text" in data
    assert "valid_romanian_word" in data
    assert "cefr_level" in data
    assert "confidence" in data
    assert "method" in data
    assert "explanation" in data
    assert "note" in data


def test_difficulty_note_mentions_phase2(client):
    response = client.post("/difficulty/", json={"text": "casă"})
    data = response.json()
    assert "Phase 2" in data["note"]


def test_difficulty_empty_text(client):
    response = client.post("/difficulty/", json={"text": ""})
    assert response.status_code == 400


def test_difficulty_technical_word(client):
    response = client.post("/difficulty/", json={"text": "hipostază"})
    assert response.status_code == 200
    data = response.json()
    assert "valid_romanian_word" in data
