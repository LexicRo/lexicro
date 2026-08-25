"""HTTP-level contract tests for /conjugate.

The transformation rules are unit-tested in test_conjugate_transform.py. These
assert the things only the HTTP layer can break: status codes, serialisation,
and the fields the OpenAPI schema promises.
"""

import json


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_known_verb_returns_the_documented_shape(client):
    response = client.get("/conjugate/merge")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"input", "notes", "verb", "moods"}
    assert data["verb"]["provenance"] == "template"


def test_the_a_prefix_is_accepted_and_gives_identical_moods(client):
    bare = client.get("/conjugate/merge").json()
    prefixed = client.get("/conjugate/a merge").json()
    assert prefixed["input"] == "a merge"
    assert prefixed["moods"] == bare["moods"]


def test_an_invented_verb_returns_200_and_says_it_guessed(client):
    # ADR-0022: report the uncertainty, do not hide the result
    response = client.get("/conjugate/xyzzyti")
    assert response.status_code == 200
    assert response.json()["verb"]["provenance"] == "predicted"


def test_an_unrecognisable_verb_returns_404(client):
    response = client.get("/conjugate/asdfgh")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_blank_input_returns_400(client):
    response = client.get("/conjugate/%20%20")
    assert response.status_code == 400


def test_every_response_carries_the_notes(client):
    data = client.get("/conjugate/merge").json()
    assert data["notes"][0]["scope"] == "all"
    assert data["notes"][0]["code"] == "upstream_unverified"
    assert data["notes"][1]["scope"] == "imperativ"


def test_pronoun_is_present_and_null_rather_than_omitted(client):
    # response_model_exclude_none would drop this; the contract requires it
    data = client.get("/conjugate/merge").json()
    entry = data["moods"]["gerunziu"]["gerunziu"][0]
    assert "pronoun" in entry
    assert entry["pronoun"] is None


def test_the_conditional_is_served(client):
    data = client.get("/conjugate/merge").json()
    assert data["moods"]["condi\u021bional"]["prezent"][0]["form"] == "a\u0219 merge"


def test_the_imperative_has_two_entries_per_tense(client):
    data = client.get("/conjugate/merge").json()
    assert len(data["moods"]["imperativ"]["imperativ"]) == 2
    assert len(data["moods"]["imperativ"]["negativ"]) == 2


def test_face_does_not_serve_the_corrupt_template(client):
    body = client.get("/conjugate/face").text
    assert "fudrir" not in body


def test_no_legacy_cedilla_in_forms_or_mood_names(client):
    data = client.get("/conjugate/merge").json()
    data["verb"]["template"] = ""  # upstream identifier, exempt
    body = json.dumps(data, ensure_ascii=False)
    assert "\u015f" not in body
    assert "\u0163" not in body


def test_minti_still_returns_the_upstream_defect(client):
    """Characterisation test. Pins a defect we deliberately did not fix.

    verbecc's present tense of `a min\u021bi` is wrong -- "eu mit" for "eu
    mint". ADR-0026 chose to report it upstream rather than correct it here.

    WHEN THIS TEST FAILS, THAT IS GOOD NEWS: upstream has fixed it. Do not
    "repair" the test. Move the verbecc pin, then re-scope the imperative note
    in conjugate_transform.py to whatever is still wrong. The general
    `upstream_unverified` note stays regardless -- see the ADR.
    """
    data = client.get("/conjugate/min\u021bi").json()
    forms = [e["form"] for e in data["moods"]["indicativ"]["prezent"]]
    assert "mit" in forms, "verbecc may have fixed the dezmi:n\u0163i template"


def test_the_conjugate_guide_is_served(client):
    response = client.get("/guide/conjugate")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_the_guide_documents_the_limitations_rather_than_hiding_them(client):
    body = client.get("/guide/conjugate").text
    assert "min\u021bi" in body          # the indicative defect
    assert "transitiv" in body.lower()   # the imperative ambiguity
    assert "verbecc" in body
