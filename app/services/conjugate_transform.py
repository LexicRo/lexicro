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


def expand(entry: dict, source: str = "verbecc") -> list[dict]:
    """One verbecc entry becomes one response entry per form it holds.

    `c` is a list. It is length 1 for all but a handful of entries -- `a avea`
    has two present-tense forms per person, the short auxiliary and the long
    main verb, both correct. Both are returned, with identical feats, in
    verbecc's order. Taking element zero would present `el a` as the present
    tense of `a avea`, which is the worse of the two to show alone; ranking
    them is a judgement LexicRo does not make.

    A tense array is therefore NOT guaranteed to hold one entry per
    person/number. The guide says so.
    """
    pronoun = entry.get("pr")
    feats = ud_feats(entry)
    return [
        {
            "form": normalise(strip_pronoun(form, pronoun)),
            "pronoun": pronoun,
            "feats": dict(feats),
            "source": source,
        }
        for form in entry["c"]
    ]


# The imperative is second person, singular then plural. LexicRo supplies the
# categories because verbecc does not: its Romanian imperative entries carry no
# `p` or `n` at all (see below).
_IMPERATIVE_SLOTS = (("tu", "Sing"), ("voi", "Plur"))


def imperative_entries(raw_entries: list[dict]) -> list[dict]:
    """The two real imperative entries, out of the sixteen verbecc returns.

    verbecc 2.0.2 emits both forms crossed with all eight pronouns -- an
    imperative for `eu` and `noi`, which Romanian does not have. The cause is a
    one-line mapping error upstream (Romanian is pointed at the Italian
    imperative person list), which also leaves `p` and `n` unset on every
    entry. Reported upstream; not corrected here.

    Filtering on `pr in ("tu", "voi")` would return FOUR entries, because both
    forms appear under both pronouns. Slicing on a single pronoun instead
    de-duplicates the eight-fold repetition and leaves the distinct forms in
    order: first 2sg, second 2pl.

    Once upstream fixes the mapping the entries arrive correctly typed and
    there are only two of them, at which point the slice would find one. So the
    typed shape is preferred when present. Both paths are tested; do not
    simplify this to either branch alone, and do not make it positional.

    In the typed branch, each entry's slot is decided by its own `n` (via the
    existing `_NUMBER` map), never by input order or a sort. An entry whose
    `n` is missing or not one of the recognised values is dropped rather than
    guessed into a slot: a mislabelled entry is worse than a missing one.
    """
    typed = [e for e in raw_entries if e.get("p") == "2"]
    if typed:
        by_number = {_NUMBER[e["n"]]: e for e in typed if e.get("n") in _NUMBER}
        ordered = [
            (by_number[number], pronoun, number)
            for pronoun, number in _IMPERATIVE_SLOTS
            if number in by_number
        ]
    else:
        untyped = [e for e in raw_entries if e.get("pr") == "tu"]
        ordered = [
            (entry, pronoun, number)
            for entry, (pronoun, number) in zip(untyped, _IMPERATIVE_SLOTS)
        ]

    result: list[dict] = []
    for entry, pronoun, number in ordered:
        for expanded in expand(entry):
            expanded["pronoun"] = pronoun
            expanded["feats"] = {"Person": "2", "Number": number}
            result.append(expanded)
    return result


# The Romanian conditional auxiliary. Invariant: it does not vary by
# conjugation class, person-stem or irregularity -- `a fi` itself gives
# "a\u0219 fi", "a\u0219 fi fost" -- which is what makes synthesising this mood
# paradigm application rather than a grammatical judgement.
_CONDITIONAL = (
    ("eu", "a\u0219", {"Person": "1", "Number": "Sing"}),
    ("tu", "ai", {"Person": "2", "Number": "Sing"}),
    ("el", "ar", {"Person": "3", "Number": "Sing", "Gender": "Masc"}),
    ("ea", "ar", {"Person": "3", "Number": "Sing", "Gender": "Fem"}),
    ("noi", "am", {"Person": "1", "Number": "Plur"}),
    ("voi", "a\u021bi", {"Person": "2", "Number": "Plur"}),
    ("ei", "ar", {"Person": "3", "Number": "Plur", "Gender": "Masc"}),
    ("ele", "ar", {"Person": "3", "Number": "Plur", "Gender": "Fem"}),
)


def conditional_mood(infinitive: str, participle: str) -> dict[str, list[dict]]:
    """The condi\u021bional mood, which verbecc declares but does not populate.

    prezent = auxiliary + infinitive.  perfect = auxiliary + "fi" + participle.

    `infinitive` MUST come from verbecc's `verb.infinitive` -- the looked-up
    lemma -- and never from the `infinitiv` mood's generated form. The two
    differ: a corrupted template makes the mood's version of `a face` read
    "fudrir;odrir", and deriving from it would ship "a\u0219 fudrir;odrir"
    stamped `source: "derived"`.

    Every form here is `derived`. Provenance is inherited, not reset: a
    conditional built from a predicted infinitive is a guess on a guess, and
    the response's `verb.provenance` stays "predicted" to say so.
    """
    infinitive = normalise(infinitive)
    participle = normalise(participle)
    return {
        "prezent": [
            {
                "form": f"{aux} {infinitive}",
                "pronoun": pronoun,
                "feats": dict(feats),
                "source": "derived",
            }
            for pronoun, aux, feats in _CONDITIONAL
        ],
        "perfect": [
            {
                "form": f"{aux} fi {participle}",
                "pronoun": pronoun,
                "feats": dict(feats),
                "source": "derived",
            }
            for pronoun, aux, feats in _CONDITIONAL
        ],
    }


# Source-quality disclosure, required on every successful response.
#
# LexicRo does not correct verbecc's Romanian -- it reports defects upstream
# and discloses them here. A visible correction would be a claim about
# everything left uncorrected, and that claim would be false: the errors are
# not confined to the imperative.
#
# The general note therefore comes first and is NOT scoped to the imperative.
# Narrowing it to the specific defects we happen to have found would recreate
# exactly the problem it exists to avoid. If verbecc fixes the imperative, the
# second note goes and the first one stays.
#
# `code` is stable and may be relied on. `message` wording may be revised.
_NOTES: tuple[dict, ...] = (
    {
        "scope": "all",
        "code": "upstream_unverified",
        "message": (
            "Forms come from verbecc 2.0.2 and are not exhaustively verified. "
            "Known errors exist outside the imperative -- e.g. the indicative "
            "present of 'a min\u021bi' returns 'eu mit' where correct Romanian "
            "is 'eu mint'."
        ),
    },
    {
        "scope": "imperativ",
        "code": "imperative_known_errors",
        "message": (
            "The imperative has known residual errors in a small set of verbs "
            "(e.g. 'merge' returns 'merge' where correct is 'mergi'), and for "
            "some verbs the form varies by transitivity -- 'treci!' vs "
            "'trece-m\u0103!' -- so a bare verb cannot determine which was "
            "meant."
        ),
    },
)


def notes() -> list[dict]:
    """A fresh copy of the disclosure, so a caller cannot mutate the constant."""
    return [dict(note) for note in _NOTES]


_IMPERATIVE_MOOD = "imperativ"
_CONDITIONAL_MOOD = "condi\u021bional"


def transform(raw: dict, input_text: str) -> dict:
    """verbecc's raw conjugation dict as LexicRo's documented response."""
    verb = raw["verb"]
    infinitive = normalise(verb["infinitive"])

    moods: dict[str, dict[str, list[dict]]] = {}
    for mood_name, tenses in raw["moods"].items():
        mood = normalise(mood_name)
        moods[mood] = {}
        for tense_name, entries in tenses.items():
            tense = normalise(tense_name)
            if mood == _IMPERATIVE_MOOD:
                moods[mood][tense] = imperative_entries(entries)
            else:
                moods[mood][tense] = [
                    expanded for entry in entries for expanded in expand(entry)
                ]

    # The `infinitiv` mood is generated from the template, and one Romanian
    # template is corrupted with a Spanish string -- `a face` and its family
    # come out as "fudrir;odrir". `verb.infinitive` is the looked-up lemma and
    # is intact, so it serves the same datum from the same source.
    #
    # This is not a correction of verbecc's Romanian. LexicRo does not make
    # those. It is choosing the uncorrupted of two copies verbecc itself
    # supplies, which is why `source` stays "verbecc".
    moods["infinitiv"] = {
        "afirmativ": [
            {
                "form": infinitive,
                "pronoun": None,
                "feats": {},
                "source": "verbecc",
            }
        ]
    }

    # The `contraf:ace` template is corrupted in a second place besides the
    # `infinitiv` mood: verbecc's `imperativ.negativ` 2sg entry is generated
    # from the same broken pipeline, so `a face` and its family come out as
    # "nu fudrir;odrir" there too. The same defect also hits `a avea` ("nu
    # aai") and `a vrea` ("nu eni") via different corrupted templates.
    #
    # Romanian's negative imperative 2sg is invariantly "nu" + infinitive --
    # there is no verb where it legitimately differs from that paradigm --
    # so composing it substitutes no linguistic judgement. `source` is
    # "derived" rather than "verbecc" (matching `conditional_mood`, which
    # composes the same auxiliary/particle-plus-infinitive shape), even
    # though the composed value is byte-identical to verbecc's own for most
    # verbs: understating our source's authority is the safe direction.
    #
    # 2pl is NOT touched here. It is a different paradigm ("nu" + the plural
    # imperative, not "nu" + infinitive) and is not part of this ruling.
    for entry in moods[_IMPERATIVE_MOOD]["negativ"]:
        if entry["pronoun"] == "tu":
            entry["form"] = f"nu {infinitive}"
            entry["source"] = "derived"

    participle = raw["moods"]["participiu"]["participiu"][0]["c"][0]
    moods[_CONDITIONAL_MOOD] = conditional_mood(infinitive, participle)

    return {
        "input": input_text,
        "notes": notes(),
        "verb": {
            "infinitive": infinitive,
            # `predicted` is verbecc's word for "I did not know this verb, so I
            # guessed a template". Promoted out of metadata and renamed,
            # because it is the fabrication signal a caller most needs.
            "provenance": "predicted" if verb.get("predicted") else "template",
            # An upstream identifier, passed through verbatim -- cedillas and
            # all. It is what a support conversation about a wrong conjugation
            # turns on, and normalising it would break that.
            "template": verb.get("template"),
        },
        "moods": moods,
    }
