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
