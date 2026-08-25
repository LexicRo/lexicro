"""Unit tests for the pure verbecc-to-contract transformation."""

import pytest

from app.services.conjugate_transform import normalise, strip_pronoun, ud_feats


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
