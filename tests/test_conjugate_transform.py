"""Unit tests for the pure verbecc-to-contract transformation."""

import json
import logging

import pytest
from verbecc import CompleteConjugator

from app.services.conjugate_transform import (
    conditional_mood,
    expand,
    imperative_entries,
    normalise,
    notes,
    strip_pronoun,
    transform,
    ud_feats,
)

logging.getLogger("verbecc").setLevel(logging.ERROR)

_conjugator = CompleteConjugator(lang="ro")


def raw(verb: str) -> dict:
    return json.loads(_conjugator.conjugate(verb).to_json())


def test_normalise_replaces_t_cedilla():
    # U+0163 t-cedilla -> U+021B t-comma-below
    assert normalise("merge\u0163i") == "merge\u021bi"


def test_normalise_replaces_s_cedilla():
    # U+015F s-cedilla -> U+0219 s-comma-below
    assert normalise("g\u0103se\u015fte") == "g\u0103se\u0219te"


def test_normalise_leaves_correct_diacritics_alone():
    assert normalise("g\u0103se\u0219te") == "g\u0103se\u0219te"


def test_normalise_leaves_other_romanian_letters_alone():
    # a-breve, a-circumflex and i-circumflex are unaffected
    assert normalise("c\u00e2nt\u0103 \u00eenainte") == "c\u00e2nt\u0103 \u00eenainte"


def test_ud_feats_maps_person_and_number():
    assert ud_feats({"n": "s", "p": "1"}) == {"Person": "1", "Number": "Sing"}


def test_ud_feats_maps_plural():
    assert ud_feats({"n": "p", "p": "2"}) == {"Person": "2", "Number": "Plur"}


def test_ud_feats_includes_gender_when_present():
    assert ud_feats({"n": "s", "p": "3", "g": "f"}) == {
        "Person": "3",
        "Number": "Sing",
        "Gender": "Fem",
    }


def test_ud_feats_omits_absent_keys_rather_than_nulling_them():
    # gerunziu/participiu/infinitiv entries carry no categories at all, and
    # verbecc's imperative entries carry no person or number either
    assert ud_feats({}) == {}
    assert "Gender" not in ud_feats({"n": "s", "p": "1"})


def test_strip_pronoun_removes_the_prefix():
    assert strip_pronoun("eu merg", "eu") == "merg"
    assert strip_pronoun("el merge", "el") == "merge"


def test_strip_pronoun_keeps_the_rest_of_a_compound_form():
    assert strip_pronoun("eu s\u0103 merg", "eu") == "s\u0103 merg"
    assert strip_pronoun("eu voi merge", "eu") == "voi merge"


def test_strip_pronoun_leaves_forms_that_do_not_carry_one():
    # the negative imperative is "nu merge" with pr "el" -- the pronoun is
    # recorded but is not a prefix, so nothing may be stripped
    assert strip_pronoun("nu merge", "el") == "nu merge"
    # the affirmative imperative likewise
    assert strip_pronoun("merge", "tu") == "merge"


def test_strip_pronoun_handles_a_null_pronoun():
    assert strip_pronoun("mergand", None) == "mergand"


def test_expand_produces_one_entry_for_one_form():
    assert expand({"c": ["eu merg"], "n": "s", "p": "1", "pr": "eu"}) == [
        {
            "form": "merg",
            "pronoun": "eu",
            "feats": {"Person": "1", "Number": "Sing"},
            "source": "verbecc",
        }
    ]


def test_expand_produces_one_entry_per_form_when_verbecc_gives_two():
    # a avea, indicativ prezent 3sg: both forms are correct Romanian
    result = expand(
        {"c": ["el a", "el are"], "g": "m", "n": "s", "p": "3", "pr": "el"}
    )
    assert [e["form"] for e in result] == ["a", "are"]
    # identical feats on both -- neither form is ranked
    assert result[0]["feats"] == result[1]["feats"]
    assert result[0]["feats"] == {"Person": "3", "Number": "Sing", "Gender": "Masc"}
    # but not the same dict -- mutating one must not corrupt the other
    assert result[0]["feats"] is not result[1]["feats"]


def test_expand_normalises_diacritics_in_the_form():
    result = expand({"c": ["voi merge\u0163i"], "n": "p", "p": "2", "pr": "voi"})
    assert result[0]["form"] == "merge\u021bi"


def test_expand_gives_a_null_pronoun_when_verbecc_reports_none():
    result = expand({"c": ["merg\u00e2nd"]})
    assert result == [
        {"form": "merg\u00e2nd", "pronoun": None, "feats": {}, "source": "verbecc"}
    ]


def test_expand_accepts_an_explicit_source():
    result = expand({"c": ["eu merg"], "n": "s", "p": "1", "pr": "eu"}, source="derived")
    assert result[0]["source"] == "derived"


def _verbecc_shaped_imperative():
    """The 16-entry shape verbecc 2.0.2 actually returns.

    Two forms, each repeated across all eight pronouns, with no person or
    number recorded.
    """
    pronouns = ["eu", "tu", "el", "ea", "noi", "voi", "ei", "ele"]
    entries = []
    for form in ("merge", "merge\u0163i"):
        for pr in pronouns:
            entries.append({"c": [form], "pr": pr})
    return entries


def test_imperative_filters_sixteen_entries_down_to_two():
    result = imperative_entries(_verbecc_shaped_imperative())
    assert len(result) == 2


def test_imperative_assigns_second_person_singular_then_plural():
    result = imperative_entries(_verbecc_shaped_imperative())
    assert result[0]["form"] == "merge"
    assert result[0]["pronoun"] == "tu"
    assert result[0]["feats"] == {"Person": "2", "Number": "Sing"}
    assert result[1]["form"] == "merge\u021bi"
    assert result[1]["pronoun"] == "voi"
    assert result[1]["feats"] == {"Person": "2", "Number": "Plur"}


def test_imperative_drops_the_impossible_pronouns():
    result = imperative_entries(_verbecc_shaped_imperative())
    assert {e["pronoun"] for e in result} == {"tu", "voi"}


def test_imperative_survives_upstream_fixing_the_person_list():
    """The shape verbecc will return once grammar_defines.py:91 is fixed.

    Two entries, correctly typed. A positional filter would return the right
    answer today and silently the wrong one after that upgrade; this asserts
    the filter is not positional.
    """
    fixed = [
        {"c": ["mergi"], "n": "s", "p": "2", "pr": "tu"},
        {"c": ["merge\u0163i"], "n": "p", "p": "2", "pr": "voi"},
    ]
    result = imperative_entries(fixed)
    assert [e["form"] for e in result] == ["mergi", "merge\u021bi"]
    assert result[0]["feats"] == {"Person": "2", "Number": "Sing"}
    assert result[1]["feats"] == {"Person": "2", "Number": "Plur"}


def test_imperative_handles_the_negative_tense_identically():
    pronouns = ["eu", "tu", "el", "ea", "noi", "voi", "ei", "ele"]
    entries = []
    for form in ("nu merge", "nu merge\u0163i"):
        for pr in pronouns:
            entries.append({"c": [form], "pr": pr})
    result = imperative_entries(entries)
    # "nu" is not a pronoun and must survive the split intact
    assert [e["form"] for e in result] == ["nu merge", "nu merge\u021bi"]


def test_imperative_typed_branch_is_not_positional():
    """Ordering comes from each entry's own `n`, not from input position.

    Feeding the typed shape plural-first must still come back singular
    first. Deriving the slot from input order rather than from `n` would
    fail this.
    """
    reversed_order = [
        {"c": ["merge\u0163i"], "n": "p", "p": "2", "pr": "voi"},
        {"c": ["mergi"], "n": "s", "p": "2", "pr": "tu"},
    ]
    result = imperative_entries(reversed_order)
    assert [e["form"] for e in result] == ["mergi", "merge\u021bi"]
    assert result[0]["feats"] == {"Person": "2", "Number": "Sing"}
    assert result[1]["feats"] == {"Person": "2", "Number": "Plur"}


def test_imperative_typed_branch_drops_entries_with_unrecognised_number():
    """A typed entry with a missing/unexpected `n` must not be mislabelled.

    verbecc never sets `p` on today's Romanian imperative entries, so this
    input is degenerate against the live install -- but it is exactly the
    shape "upstream ships `p` but omits `n`" would take, which is the case
    the typed branch exists for. The entry with no recognisable `n` is
    dropped rather than guessed into a slot; only the plural entry survives.
    """
    degenerate = [
        {"c": ["mergi"], "p": "2", "pr": "tu"},
        {"c": ["merge\u0163i"], "n": "p", "p": "2", "pr": "voi"},
    ]
    result = imperative_entries(degenerate)
    assert [e["form"] for e in result] == ["merge\u021bi"]
    assert result[0]["pronoun"] == "voi"
    assert result[0]["feats"] == {"Person": "2", "Number": "Plur"}


def test_conditional_prezent_is_auxiliary_plus_infinitive():
    mood = conditional_mood("merge", "mers")
    forms = [e["form"] for e in mood["prezent"]]
    assert forms == [
        "a\u0219 merge",
        "ai merge",
        "ar merge",
        "ar merge",
        "am merge",
        "a\u021bi merge",
        "ar merge",
        "ar merge",
    ]


def test_conditional_perfect_is_auxiliary_plus_fi_plus_participle():
    mood = conditional_mood("merge", "mers")
    assert mood["perfect"][0]["form"] == "a\u0219 fi mers"
    assert mood["perfect"][5]["form"] == "a\u021bi fi mers"


def test_conditional_pronouns_match_the_indicative_set():
    mood = conditional_mood("merge", "mers")
    assert [e["pronoun"] for e in mood["prezent"]] == [
        "eu", "tu", "el", "ea", "noi", "voi", "ei", "ele",
    ]


def test_conditional_carries_gendered_third_person_feats():
    mood = conditional_mood("merge", "mers")
    assert mood["prezent"][2]["feats"] == {
        "Person": "3", "Number": "Sing", "Gender": "Masc",
    }
    assert mood["prezent"][3]["feats"] == {
        "Person": "3", "Number": "Sing", "Gender": "Fem",
    }
    assert mood["prezent"][0]["feats"] == {"Person": "1", "Number": "Sing"}


def test_conditional_forms_are_all_marked_derived():
    mood = conditional_mood("merge", "mers")
    assert all(e["source"] == "derived" for e in mood["prezent"])
    assert all(e["source"] == "derived" for e in mood["perfect"])


def test_conditional_of_a_fi_is_not_special_cased():
    mood = conditional_mood("fi", "fost")
    assert mood["prezent"][0]["form"] == "a\u0219 fi"
    assert mood["perfect"][0]["form"] == "a\u0219 fi fost"


def test_conditional_normalises_its_inputs():
    mood = conditional_mood("min\u0163i", "min\u0163it")
    assert mood["prezent"][0]["form"] == "a\u0219 min\u021bi"
    assert mood["perfect"][0]["form"] == "a\u0219 fi min\u021bit"


def test_conditional_feats_do_not_share_identity_between_prezent_and_perfect():
    mood = conditional_mood("merge", "mers")
    for i in range(len(mood["prezent"])):
        assert mood["prezent"][i]["feats"] is not mood["perfect"][i]["feats"]


def test_notes_are_general_first_then_specific():
    result = notes()
    assert result[0]["scope"] == "all"
    assert result[1]["scope"] == "imperativ"


def test_notes_carry_stable_codes():
    codes = [n["code"] for n in notes()]
    assert codes == ["upstream_unverified", "imperative_known_errors"]


def test_the_general_note_names_a_defect_outside_the_imperative():
    # ADR-0026: an imperative-only caveat implicitly certifies the other seven
    # moods, and the min\u021bi indicative proves that certification false. If
    # this assertion is ever "simplified" away, read the ADR before doing it.
    general = notes()[0]["message"]
    assert "min\u021bi" in general
    assert "indicative" in general.lower()


def test_notes_are_a_fresh_list_each_call():
    # a caller mutating the response must not corrupt the module constant
    first = notes()
    first.append({"scope": "bogus", "code": "x", "message": "y"})
    assert len(notes()) == 2
    # the list being fresh is not enough on its own: `return list(_NOTES)`
    # would pass the assertion above while still handing out the SAME dict
    # objects held in _NOTES, letting a caller corrupt the constant with
    # `notes()[0]["message"] = "x"`. The dicts must be fresh too.
    assert notes()[0] is not notes()[0]


def test_note_text_uses_comma_below_diacritics_only():
    for note in notes():
        assert "\u015f" not in note["message"]
        assert "\u0163" not in note["message"]


def test_transform_echoes_the_input_verbatim():
    result = transform(raw("merge"), "a merge")
    assert result["input"] == "a merge"


def test_transform_reports_template_provenance_for_a_known_verb():
    result = transform(raw("merge"), "merge")
    assert result["verb"]["provenance"] == "template"
    assert result["verb"]["infinitive"] == "merge"
    assert result["verb"]["template"] == "concu:rge"


def test_transform_reports_predicted_provenance_for_an_invented_verb():
    result = transform(raw("xyzzyti"), "xyzzyti")
    assert result["verb"]["provenance"] == "predicted"


def test_transform_uses_ud_vocabulary_not_single_letters():
    result = transform(raw("merge"), "merge")
    first = result["moods"]["indicativ"]["prezent"][0]
    assert first == {
        "form": "merg",
        "pronoun": "eu",
        "feats": {"Person": "1", "Number": "Sing"},
        "source": "verbecc",
    }


def test_transform_includes_the_synthesised_conditional():
    result = transform(raw("merge"), "merge")
    prezent = result["moods"]["condi\u021bional"]["prezent"]
    assert prezent[0]["form"] == "a\u0219 merge"
    assert prezent[0]["source"] == "derived"
    assert result["moods"]["condi\u021bional"]["perfect"][0]["form"] == "a\u0219 fi mers"


def test_transform_filters_both_imperative_tenses():
    result = transform(raw("merge"), "merge")
    assert len(result["moods"]["imperativ"]["imperativ"]) == 2
    assert len(result["moods"]["imperativ"]["negativ"]) == 2


def test_transform_serves_the_clean_infinitive_for_the_face_family():
    """verbecc's `infinitiv` mood for `a face` is a corrupted Spanish string.

    conjugations-ro.xml:7180 holds "udrir;odrir" in the contraf:ace template.
    `verb.infinitive` is intact, so that is what the mood serves -- still
    verbecc's own value for the same datum, hence source "verbecc".
    """
    for verb in ("face", "desface", "reface"):
        result = transform(raw(verb), verb)
        serialised = json.dumps(result, ensure_ascii=False)
        assert "fudrir" not in serialised, f"{verb} leaked the corrupt template"
        assert result["moods"]["infinitiv"]["afirmativ"][0]["form"] == verb
        assert result["moods"]["infinitiv"]["afirmativ"][0]["source"] == "verbecc"


def test_transform_does_not_derive_the_conditional_from_the_corrupt_infinitive():
    result = transform(raw("face"), "face")
    assert result["moods"]["condi\u021bional"]["prezent"][0]["form"] == "a\u0219 face"


def test_transform_gives_a_null_pronoun_to_moods_that_take_none():
    result = transform(raw("merge"), "merge")
    for mood, tense in (
        ("infinitiv", "afirmativ"),
        ("gerunziu", "gerunziu"),
        ("participiu", "participiu"),
    ):
        entry = result["moods"][mood][tense][0]
        assert entry["pronoun"] is None
        assert entry["feats"] == {}


def test_transform_emits_no_legacy_cedilla_anywhere():
    for verb in ("merge", "min\u021bi", "face", "g\u0103si"):
        result = transform(raw(verb), verb)
        # verb.template is an upstream identifier, not Romanian prose, and is
        # deliberately passed through with verbecc's spelling. Drop it before
        # asserting on everything else.
        result["verb"]["template"] = ""
        body = json.dumps(result, ensure_ascii=False)
        assert "\u015f" not in body, f"s-cedilla leaked for {verb}"
        assert "\u0163" not in body, f"t-cedilla leaked for {verb}"


def test_transform_keeps_the_template_identifier_verbatim():
    # dezmi:n\u0163i is verbecc's name for the template. Normalising it would
    # produce a string that matches no verbecc template.
    result = transform(raw("min\u021bi"), "min\u021bi")
    assert result["verb"]["template"] == "dezmi:n\u0163i"


def test_transform_attaches_the_notes():
    result = transform(raw("merge"), "merge")
    assert [n["code"] for n in result["notes"]] == [
        "upstream_unverified",
        "imperative_known_errors",
    ]


def test_transform_drops_verbecc_internals():
    result = transform(raw("merge"), "merge")
    assert "lang" not in result["verb"]
    assert "stem" not in result["verb"]
    assert "translation_en" not in result["verb"]
    assert "predicted" not in result["verb"]


def test_transform_keeps_both_forms_of_avea_in_the_present():
    result = transform(raw("avea"), "avea")
    third_sing = [
        e
        for e in result["moods"]["indicativ"]["prezent"]
        if e["pronoun"] == "el"
    ]
    assert [e["form"] for e in third_sing] == ["a", "are"]


def test_transform_derives_the_negative_imperative_2sg_for_the_face_family():
    """The `contraf:ace` template is corrupted in two places, not one: the
    `infinitiv` mood and `imperativ.negativ` 2sg both come out as
    "fudrir;odrir" (see the task-8 report). Romanian's negative imperative
    2sg is invariantly "nu" + infinitive for every verb, so it is composed
    the same way the `infinitiv` mood is served, and marked "derived" per
    the ruling -- matching `conditional_mood`'s provenance for the same
    auxiliary/particle-plus-infinitive shape.

    2pl is untouched: verbecc's own value for this family is correct, and
    the ruling scopes the fix to 2sg only.
    """
    for verb in ("face", "desface", "reface"):
        result = transform(raw(verb), verb)
        negativ = result["moods"]["imperativ"]["negativ"]
        second_person_singular = [e for e in negativ if e["pronoun"] == "tu"][0]
        second_person_plural = [e for e in negativ if e["pronoun"] == "voi"][0]
        assert second_person_singular["form"] == f"nu {verb}"
        assert second_person_singular["source"] == "derived"
        assert second_person_plural["source"] == "verbecc"


def test_transform_derives_the_negative_imperative_2sg_for_further_corrupted_verbs():
    """`a avea` and `a vrea` carry the same two-site corruption pattern as
    `a face`, via different broken templates: verbecc's raw
    imperativ.negativ 2sg gives "nu aai" for avea and "nu eni" for vrea --
    neither is a Romanian word. Composed from verb.infinitive instead, same
    fix and provenance as the face family.

    2pl is a separate, still-open defect for these two verbs specifically
    (verbecc's 2pl value is *also* wrong here, unlike the face family) --
    see the task-8 report. It is deliberately not touched by this test or
    by the fix; the ruling scopes the fix to 2sg only.
    """
    for verb, forbidden in (("avea", "aai"), ("vrea", "eni")):
        result = transform(raw(verb), verb)
        second_person_singular = [
            e
            for e in result["moods"]["imperativ"]["negativ"]
            if e["pronoun"] == "tu"
        ][0]
        assert forbidden not in second_person_singular["form"]
        assert second_person_singular["form"] == f"nu {verb}"
        assert second_person_singular["source"] == "derived"


def test_transform_leaves_the_affirmative_imperative_untouched_for_a_corrupt_verb():
    """The disclosure rule is deliberately asymmetric: the negative
    imperative 2sg is composed when verbecc's own template is corrupt, but
    the affirmative imperative is passed through uncorrected, non-word and
    all. `a avea`'s affirmative 2sg imperative is "aai" -- the same broken
    template that also corrupts the negative -- and it must still read that
    way, `source: "verbecc"`, not silently fixed. This is exactly the kind
    of asymmetry a later "tidy-up" would erase without a test pinning it.
    """
    result = transform(raw("avea"), "avea")
    affirmativ = result["moods"]["imperativ"]["imperativ"]
    second_person_singular = [e for e in affirmativ if e["pronoun"] == "tu"][0]
    assert second_person_singular["form"] == "aai"
    assert second_person_singular["source"] == "verbecc"


def test_transform_composes_the_negative_imperative_2sg_only_where_intended():
    """The sweep a single-verb assertion cannot provide: proof the
    composition is correctly SCOPED, not merely that it fires somewhere.

    Three verbs, three different intended outcomes:

    - merge: a normal personal verb whose data is already intact. The
      composed 2sg must be byte-identical to what verbecc itself returns
      for that entry -- composing must not change a form that needed no
      fixing.
    - ninge: impersonal, has no imperative. verbecc marks every person with
      the "-" sentinel, and composition must leave it alone rather than
      fabricate "nu ninge" for a verb that has no imperative at all.
    - face: a corrupted template ("nu fudrir;odrir"). Composition must
      replace it with "nu face", `source: "derived"`.
    """
    merge_raw = raw("merge")
    merge_expected_form = next(
        entry["c"][0]
        for entry in merge_raw["moods"]["imperativ"]["negativ"]
        if entry.get("pr") == "tu"
    )
    merge_result = transform(merge_raw, "merge")
    merge_2sg = next(
        e
        for e in merge_result["moods"]["imperativ"]["negativ"]
        if e["pronoun"] == "tu"
    )
    assert merge_2sg["form"] == merge_expected_form
    assert merge_2sg["source"] == "derived"

    ninge_result = transform(raw("ninge"), "ninge")
    ninge_2sg = next(
        e
        for e in ninge_result["moods"]["imperativ"]["negativ"]
        if e["pronoun"] == "tu"
    )
    assert ninge_2sg["form"] == "-"
    assert ninge_2sg["source"] == "verbecc"

    face_result = transform(raw("face"), "face")
    face_2sg = next(
        e
        for e in face_result["moods"]["imperativ"]["negativ"]
        if e["pronoun"] == "tu"
    )
    assert face_2sg["form"] == "nu face"
    assert face_2sg["source"] == "derived"


from app.services.verbecc_service import EmptyVerbError, conjugate_verb  # noqa: E402


def test_conjugate_verb_rejects_empty_input_before_calling_verbecc():
    with pytest.raises(EmptyVerbError):
        conjugate_verb("")


def test_conjugate_verb_rejects_whitespace_and_a_bare_prefix():
    with pytest.raises(EmptyVerbError):
        conjugate_verb("   ")
    with pytest.raises(EmptyVerbError):
        conjugate_verb("a ")


def test_conjugate_verb_still_raises_plain_value_error_for_an_unknown_verb():
    with pytest.raises(ValueError) as excinfo:
        conjugate_verb("asdfgh")
    assert not isinstance(excinfo.value, EmptyVerbError)
