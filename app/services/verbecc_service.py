"""Thin access layer over verbecc. Shaping lives in conjugate_transform."""

import json
import logging

from verbecc import CompleteConjugator

logging.getLogger("verbecc").setLevel(logging.ERROR)

_conjugator = CompleteConjugator(lang="ro")


class EmptyVerbError(ValueError):
    """No verb was supplied. Distinct from `not found` -- it is a 400, not 404."""


def conjugate_verb(verb: str) -> dict:
    """The full conjugation table verbecc returns, unshaped.

    Accepts the verb with or without the Romanian infinitive prefix `a`.
    Raises EmptyVerbError for blank input and ValueError when verbecc cannot
    produce a conjugation.
    """
    normalised = verb.strip().lower()
    if normalised.startswith("a "):
        normalised = normalised[2:].strip()
    elif normalised == "a":
        # The bare infinitive particle with nothing after it -- e.g. "a "
        # loses its trailing space to the .strip() above and lands here
        # rather than in the prefix branch. Still no verb was supplied.
        normalised = ""

    if not normalised:
        raise EmptyVerbError(
            "No verb supplied. Provide the infinitive, e.g. 'trezi' or 'a trezi'."
        )

    try:
        return json.loads(_conjugator.conjugate(normalised).to_json())
    except Exception as exc:
        raise ValueError(
            f"Verb '{verb}' not found. "
            f"Please provide the infinitive form (e.g. 'trezi' or 'a trezi')."
        ) from exc
