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


def test_minti_returns_the_corrected_present(client):
    """The defect this test used to pin was fixed upstream in verbecc 2.0.3.

    Until 2026-08-27 this asserted the opposite -- that `a min\u021bi` returned
    "eu mit" -- as a characterisation test under ADR-0026. It failed when the
    pin moved, which is what it was there to do. Kept, inverted, so that a
    rollback of the pin is a test failure rather than a silent regression in
    what callers are served.
    """
    data = client.get("/conjugate/min\u021bi").json()
    forms = [e["form"] for e in data["moods"]["indicativ"]["prezent"]]
    assert "mint" in forms
    assert "mit" not in forms


def test_merge_still_returns_the_upstream_imperative_defect(client):
    """Characterisation test. Pins a defect we deliberately did not fix.

    verbecc serves the third person singular where `a merge`'s second person
    imperative belongs -- "merge" for "mergi" -- and likewise for `a trece`
    and `a t\u0103cea`. Reported as verbecc#50, which is open: the fix needs a
    judgement on Romanian that the maintainer has said he cannot make. ADR-0026
    chose to disclose rather than correct, and ADR-0027 decided explicitly not
    to wait on this one.

    WHEN THIS TEST FAILS, THAT IS GOOD NEWS: upstream has fixed it. Do not
    "repair" the test. Move the verbecc pin, then re-scope the
    `imperative_known_errors` note in conjugate_transform.py -- and the
    Known limitations section of docs/conjugate.md -- to whatever is still
    wrong. The general `upstream_unverified` note stays regardless.
    """
    data = client.get("/conjugate/merge").json()
    affirmativ = data["moods"]["imperativ"]["imperativ"]
    second_person_singular = [e for e in affirmativ if e["pronoun"] == "tu"][0]
    assert second_person_singular["form"] == "merge", "verbecc#50 may be fixed"


def test_the_conjugate_guide_is_served(client):
    response = client.get("/guide/conjugate")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_the_guide_documents_the_limitations_rather_than_hiding_them(client):
    body = client.get("/guide/conjugate").text
    assert "min\u021bi" in body          # the indicative defect
    assert "transitiv" in body.lower()   # the imperative ambiguity
    assert "verbecc" in body


def test_the_imperative_note_carries_its_verbs_over_the_wire(client):
    """The transform-level test for this passed while the field never reached
    a caller.

    `notes()` returned `verbs`, and `NoteOut` did not declare it, so the
    response_model dropped it silently -- no error, no warning, just an
    absent key. The demo read the field, found nothing, and flagged nothing.

    This is the layer that broke, and the one this file exists for: the
    things only the HTTP boundary can break, including the fields the schema
    promises. A model asserted through the function that builds it is not
    asserted at all.
    """
    notes = client.get("/conjugate/merge").json()["notes"]
    imperative = [n for n in notes if n["code"] == "imperative_known_errors"][0]
    assert imperative["verbs"] == ["merge", "trece", "t\u0103cea"]


def test_the_general_note_does_not_carry_verbs(client):
    """`verbs` is specific to the imperative note, and a caller iterating
    notes must be able to tell them apart by absence rather than by an empty
    list that looks like "no verbs are affected"."""
    notes = client.get("/conjugate/merge").json()["notes"]
    general = [n for n in notes if n["code"] == "upstream_unverified"][0]
    assert general.get("verbs") is None


def test_the_contradiction_note_reaches_the_wire(client):
    """ADR-0029's note, asserted at the boundary that dropped `verbs` in
    0.6.3. A field the transform produces and NoteOut does not declare is
    filtered out silently -- no error, just an absent key -- so a note is not
    shipped until a test has seen it come back over HTTP.
    """
    data = client.get("/conjugate/ninge").json()
    note = [n for n in data["notes"] if n["code"] == "paradigm_contradiction"]
    assert note, "expected the contradiction note"
    assert "indicativ/perfect-compus" in note[0]["tenses"]


def test_an_ordinary_verb_carries_only_the_standing_notes(client):
    codes = [n["code"] for n in client.get("/conjugate/merge").json()["notes"]]
    assert codes == ["upstream_unverified", "imperative_known_errors"]
