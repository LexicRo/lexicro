"""Unit tests for the pure verbecc-to-contract transformation."""

import pytest

from app.services.conjugate_transform import normalise


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
