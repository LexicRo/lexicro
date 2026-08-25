"""Unit tests for the pure verbecc-to-contract transformation."""

import pytest

from app.services.conjugate_transform import (
    expand,
    imperative_entries,
    normalise,
    strip_pronoun,
    ud_feats,
)


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
    for form in ("merge", "mergeţi"):
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
    assert result[1]["form"] == "mergeți"
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
        {"c": ["mergeţi"], "n": "p", "p": "2", "pr": "voi"},
    ]
    result = imperative_entries(fixed)
    assert [e["form"] for e in result] == ["mergi", "mergeți"]
    assert result[0]["feats"] == {"Person": "2", "Number": "Sing"}
    assert result[1]["feats"] == {"Person": "2", "Number": "Plur"}


def test_imperative_handles_the_negative_tense_identically():
    pronouns = ["eu", "tu", "el", "ea", "noi", "voi", "ei", "ele"]
    entries = []
    for form in ("nu merge", "nu mergeţi"):
        for pr in pronouns:
            entries.append({"c": [form], "pr": pr})
    result = imperative_entries(entries)
    # "nu" is not a pronoun and must survive the split intact
    assert [e["form"] for e in result] == ["nu merge", "nu mergeți"]
