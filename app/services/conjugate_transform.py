"""Turn verbecc's raw conjugation dict into LexicRo's documented contract.

Pure: dicts in, dicts out. No I/O, no FastAPI, no verbecc import -- which is
what makes every rule here unit-testable against a hand-built fixture as well
as against real output.

The rules implemented here are specified in lexicro-docs; the short version:

* verbecc's single-letter keys (c/n/p/pr/g) are not a contract, so they become
  the same UD vocabulary /analyze speaks (Number: "Sing", Person: "1").
* verbecc declares the condi\u021bional mood and ships no data for it, so LexicRo
  synthesises it from the invariant auxiliary plus verbecc's own infinitive and
  participle.
* verbecc's Romanian has known defects. LexicRo does not correct them; it
  reports them upstream and discloses them in the `notes` array. The one
  exception is a corrupted record -- see `infinitive_form`.
"""

from __future__ import annotations

# verbecc's Romanian data writes `s` with the modern comma-below (839
# occurrences) and `t` with the legacy cedilla (2205). /analyze emits
# comma-below exclusively, and two endpoints of one API must not spell
# Romanian two ways. The s-cedilla mapping never fires against 2.0.2 and is
# kept because an upstream data edit could reintroduce it at any time.
_DIACRITICS = str.maketrans({"\u015f": "\u0219", "\u0163": "\u021b"})


def normalise(text: str) -> str:
    """Legacy cedillas to Romanian's comma-below codepoints."""
    return text.translate(_DIACRITICS)


_NUMBER = {"s": "Sing", "p": "Plur"}
_GENDER = {"m": "Masc", "f": "Fem"}


def ud_feats(entry: dict) -> dict[str, str]:
    """verbecc's single-letter categories as Universal Features.

    Same vocabulary /analyze returns for the same concepts. An inapplicable
    category is absent from the dict rather than present and null, matching how
    /analyze omits features that do not apply.
    """
    feats: dict[str, str] = {}
    if entry.get("p"):
        feats["Person"] = entry["p"]
    if entry.get("n") in _NUMBER:
        feats["Number"] = _NUMBER[entry["n"]]
    if entry.get("g") in _GENDER:
        feats["Gender"] = _GENDER[entry["g"]]
    return feats


def strip_pronoun(combined: str, pronoun: str | None) -> str:
    """The inflected form without its pronoun.

    verbecc glues them together ("eu merg") but also reports the pronoun
    separately, so this is an exact split rather than string surgery. The
    prefix is only removed when it is actually there: the imperative reports a
    pronoun it does not prepend ("merge" with pr "tu"), and the negative
    imperative prepends "nu" instead ("nu merge").
    """
    if pronoun and combined.startswith(pronoun + " "):
        return combined[len(pronoun) + 1 :]
    return combined
