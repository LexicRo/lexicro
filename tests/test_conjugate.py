def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_conjugate_known_verb(client):
    response = client.get("/conjugate/merge")
    assert response.status_code == 200
    data = response.json()
    assert "moods" in data
    assert "verb" in data
    assert data["verb"]["infinitive"] == "merge"
    assert data["verb"]["predicted"] is False


def test_conjugate_with_prefix(client):
    response = client.get("/conjugate/a merge")
    assert response.status_code == 200
    data = response.json()
    assert data["verb"]["infinitive"] == "merge"


def test_conjugate_has_indicativ(client):
    response = client.get("/conjugate/merge")
    data = response.json()
    assert "indicativ" in data["moods"]
    assert "prezent" in data["moods"]["indicativ"]


def test_conjugate_prezent_first_person(client):
    response = client.get("/conjugate/merge")
    data = response.json()
    prezent = data["moods"]["indicativ"]["prezent"]
    first_person = next(e for e in prezent if e["p"] == "1" and e["n"] == "s")
    assert "eu merg" in first_person["c"]


def test_conjugate_unknown_verb(client):
    response = client.get("/conjugate/trezit")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_conjugate_another_known_verb(client):
    response = client.get("/conjugate/trezi")
    assert response.status_code == 200
    data = response.json()
    assert data["verb"]["infinitive"] == "trezi"
