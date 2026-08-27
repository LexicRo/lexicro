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
# occurrences in 2.0.3's conjugations-ro.xml) and `t` with the legacy cedilla
# (2204 -- one fewer than 2.0.2, which the `a vrea` correction accounts for).
# /analyze emits comma-below exclusively, and two endpoints of one API must
# not spell Romanian two ways. The s-cedilla mapping still never fires --
# re-counted against 2.0.3, which contains no U+015F at all -- and is kept
# because an upstream data edit could reintroduce it at any time.
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
    """The two real imperative entries, whatever shape verbecc delivers them in.

    **On the pinned 2.0.3 the typed branch is the live one.** verbecc 2.0.2
    emitted both forms crossed with all eight pronouns -- an imperative for
    `eu` and `noi`, which Romanian does not have -- because Romanian was
    pointed at the Italian imperative person list, which also left `p` and `n`
    unset on every entry. That was reported upstream and fixed in 2.0.3
    (verbecc PR #47): entries now arrive correctly typed, two of them.

    The untyped branch below is therefore dormant, and is kept deliberately.
    It is what makes the pin reversible, and the eight-fold shape is not
    guaranteed gone for good. Under it, filtering on `pr in ("tu", "voi")`
    would return FOUR entries, because both forms appear under both pronouns;
    slicing on a single pronoun de-duplicates the repetition and leaves the
    distinct forms in order: first 2sg, second 2pl. That same slice would find
    only one entry against typed input, which is why the typed shape is
    preferred when present.

    Both paths are tested; do not simplify this to either branch alone, and do
    not make it positional.

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


# verbecc's sentinel for "this form does not exist", used for 267 of the
# 6,864 Romanian verbs -- the impersonal and defective ones. Two rules read
# it: the conditional mirrors it rather than synthesising a person the verb
# does not have, and the negative imperative refuses to overwrite it.
_NONEXISTENT_FORM = "-"


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


def conditional_mood(
    infinitive: str,
    participle: str,
    indicative_prezent: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """The condi\u021bional mood, which verbecc declares but does not populate.

    prezent = auxiliary + infinitive.  perfect = auxiliary + "fi" + participle.

    `infinitive` MUST come from verbecc's `verb.infinitive` -- the looked-up
    lemma -- and never from the `infinitiv` mood's generated form. The two can
    differ: in 2.0.2 a corrupted template made the mood's version of `a face`
    read "fudrir;odrir", and deriving from it would have shipped
    "a\u0219 fudrir;odrir" stamped `source: "derived"`. That template was
    fixed in 2.0.3, but the lemma remains the right source -- it is the datum
    verbecc looked up, rather than one it generated.

    Every form here is `derived`. Provenance is inherited, not reset: a
    conditional built from a predicted infinitive is a guess on a guess, and
    the response's `verb.provenance` stays "predicted" to say so.

    `indicative_prezent`, when given, is the already-transformed
    `indicativ.prezent` and decides WHICH persons exist. verbecc marks a
    person that does not exist with the "-" sentinel, and does so for 267 of
    6,864 Romanian verbs -- the impersonal and defective ones. Applying the
    paradigm to all eight regardless produced "a\u0219 ninge", a first-person
    conditional of a verb whose every personal indicative slot is "-".

    Mirroring is per person rather than per verb, because the two are not the
    same shape: `a ninge` HAS a third-person singular ("ninge") and lacks a
    third-person plural, so a verb-level "impersonal" flag would get one of
    those two wrong.

    Omitted, the mood is built for all eight as before -- callers passing two
    arguments are asking for the paradigm, not for a judgement about this verb.
    """
    infinitive = normalise(infinitive)
    participle = normalise(participle)
    absent = {
        entry["pronoun"]
        for entry in (indicative_prezent or ())
        if entry.get("form") == _NONEXISTENT_FORM
    }
    return {
        "prezent": [
            {
                "form": (
                    _NONEXISTENT_FORM
                    if pronoun in absent
                    else f"{aux} {infinitive}"
                ),
                "pronoun": pronoun,
                "feats": dict(feats),
                "source": "derived",
            }
            for pronoun, aux, feats in _CONDITIONAL
        ],
        "perfect": [
            {
                "form": (
                    _NONEXISTENT_FORM
                    if pronoun in absent
                    else f"{aux} fi {participle}"
                ),
                "pronoun": pronoun,
                "feats": dict(feats),
                "source": "derived",
            }
            for pronoun, aux, feats in _CONDITIONAL
        ],
    }


def compose_negative_imperative(negativ_entries: list[dict], infinitive: str) -> None:
    """Overwrite the negative imperative 2sg entry in place, composed rather
    than trusted from verbecc.

    This began as a defence against corrupted templates: in 2.0.2 verbecc's
    `imperativ.negativ` 2sg was generated from the same broken pipeline as the
    `infinitiv` mood, so `a face` and its family came out as
    "nu fudrir;odrir", `a avea` as "nu aai" and `a vrea` as "nu eni".
    **Those templates were corrected upstream in 2.0.3, so the rule no longer
    has a known defect to cover.** It is kept because its justification never
    depended on them: it is a paradigm, not a repair, and it fires for every
    verb rather than for a list of broken ones.

    Romanian's negative imperative 2sg is invariantly "nu" + infinitive --
    there is no verb where it legitimately differs from that paradigm -- so
    composing it substitutes no linguistic judgement. `source` is "derived"
    rather than "verbecc" (matching `conditional_mood`, which composes the
    same auxiliary/particle-plus-infinitive shape), even though the composed
    value is byte-identical to verbecc's own for most verbs: understating our
    source's authority is the safe direction.

    This does NOT fire when verbecc's own value is the "-" sentinel --
    verbecc's marker for "this verb has no such form" (267 of 6,864 verbs,
    mostly impersonal ones like `a ninge`). "-" is not a corrupted form to
    replace; it is correct, informative data, and composing "nu ninge" over
    it would fabricate an imperative for a verb that has none, under
    LexicRo's own `derived` signature. LexicRo's rule is to disclose
    verbecc's defects, not invent past its gaps.

    2pl is NOT touched here. It is a different paradigm ("nu" + the plural
    imperative, not "nu" + infinitive) and is not part of this ruling.
    """
    for entry in negativ_entries:
        if entry["pronoun"] == "tu" and entry["form"] != _NONEXISTENT_FORM:
            entry["form"] = f"nu {infinitive}"
            entry["source"] = "derived"


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
            "Forms come from verbecc 2.0.3 and are not exhaustively verified. "
            "Two defects outside the imperative -- the indicative present of "
            "'a min\u021bi', and the infinitive of 'a face' -- were reported "
            "upstream and corrected in 2.0.3. Both surfaced from spot checks "
            "rather than an audit, and the data has not been audited as a "
            "whole, so the absence of a current example is not evidence that "
            "none remain."
        ),
    },
    {
        "scope": "imperativ",
        "code": "imperative_known_errors",
        "message": (
            "The imperative has known residual errors in a small set of verbs: "
            "'a merge', 'a trece' and 'a t\u0103cea' are served their third "
            "person singular where a second person imperative belongs -- "
            "'merge' where correct Romanian is 'mergi'. Separately, for some "
            "verbs the form varies by transitivity -- 'treci!' vs "
            "'trece-m\u0103!' -- so a bare verb cannot determine which was "
            "meant."
        ),
    },
)


def notes() -> list[dict]:
    """A fresh copy of the disclosure, so a caller cannot mutate the constant."""
    return [dict(note) for note in _NOTES]


_IMPERATIVE_MOOD = "imperativ"
_INDICATIVE_MOOD = "indicativ"
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

    # The `infinitiv` mood is generated from the template. Under 2.0.2 one
    # Romanian template was corrupted with a Spanish string, so `a face` and
    # its family came out as "fudrir;odrir"; `verb.infinitive` is the
    # looked-up lemma, was intact, and serves the same datum from the same
    # source. The template was corrected upstream in 2.0.3 and the two copies
    # now agree, which makes this a no-op rather than a fix -- but the lemma
    # stays the source, because generated data is the copy that broke.
    #
    # This is not a correction of verbecc's Romanian. LexicRo does not make
    # those. It is choosing between two copies verbecc itself supplies, which
    # is why `source` stays "verbecc".
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

    compose_negative_imperative(moods[_IMPERATIVE_MOOD]["negativ"], infinitive)

    participle = raw["moods"]["participiu"]["participiu"][0]["c"][0]
    # The indicative decides which persons this verb HAS. For the 267 verbs
    # verbecc marks impersonal or defective, applying the conditional paradigm
    # to all eight without consulting it produced first- and second-person
    # conditionals of a verb with no personal forms at all.
    moods[_CONDITIONAL_MOOD] = conditional_mood(
        infinitive,
        participle,
        moods.get(_INDICATIVE_MOOD, {}).get("prezent"),
    )

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
