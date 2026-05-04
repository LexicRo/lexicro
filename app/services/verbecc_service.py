import json
from verbecc import CompleteConjugator

import logging
logging.getLogger('verbecc').setLevel(logging.ERROR)

_conjugator = CompleteConjugator(lang='ro')


def conjugate_verb(verb: str) -> dict:
    """
    Conjugate a Romanian verb using verbecc.
    Accepts verb with or without the Romanian infinitive prefix 'a'.
    Returns the full conjugation table as a dict.
    Raises ValueError if the verb is not found.
    """
    normalised = verb.strip().lower()
    if normalised.startswith("a "):
        normalised = normalised[2:]

    try:
        result = _conjugator.conjugate(normalised)
        return json.loads(result.to_json())
    except Exception as e:
        raise ValueError(
            f"Verb '{verb}' not found. "
            f"Please provide the infinitive form (e.g. 'trezi' or 'a trezi')."
        )