"""GET /conjugate/{verb} -- Romanian verb conjugation.

Models live here rather than in the service, following app/routers/analyze.py:
the router owns the contract and the OpenAPI schema, the service owns the data.

The handler is `def`, not `async def`. Conjugation is synchronous and CPU-bound,
so FastAPI runs it in its threadpool and one slow request cannot block the
event loop. Declaring it `async def` would serialise the whole service behind a
single conjugation.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.conjugate_transform import transform
from app.services.verbecc_service import EmptyVerbError, conjugate_verb

router = APIRouter(prefix="/conjugate", tags=["Conjugation"])


class NoteOut(BaseModel):
    scope: str = Field(
        ...,
        description="'all', or the name of the mood this note applies to.",
    )
    code: str = Field(
        ...,
        description=(
            "Stable machine identifier for this note. Safe to match on, "
            "suppress or localise. The `message` wording may be revised; the "
            "code will not."
        ),
    )
    message: str = Field(..., description="Human-readable text, safe to display verbatim.")


class FormOut(BaseModel):
    form: str = Field(..., description="The inflected form, without its pronoun.")
    pronoun: str | None = Field(
        ...,
        description=(
            "The pronoun this form takes, or null for moods that take none "
            "(infinitiv, gerunziu, participiu)."
        ),
    )
    feats: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Universal Features, the same vocabulary /analyze returns: Person "
            "('1'|'2'|'3'), Number ('Sing'|'Plur'), Gender ('Masc'|'Fem') on "
            "third person only. An inapplicable feature is absent, not null."
        ),
    )
    source: Literal["verbecc", "derived"] = Field(
        ...,
        description=(
            "Which system produced this FORM: 'verbecc' (the conjugation "
            "library) or 'derived' (built by LexicRo from verbecc's own "
            "output -- the whole condi\u021bional mood, which verbecc declares "
            "but does not populate). Provenance, not confidence."
        ),
    )


class VerbOut(BaseModel):
    infinitive: str = Field(..., description="The verb as looked up, without the 'a' prefix.")
    provenance: Literal["template", "predicted"] = Field(
        ...,
        description=(
            "Whether verbecc RECOGNISED this verb: 'template' (matched a known "
            "conjugation template) or 'predicted' (did not know it and guessed "
            "a template from its ending). A predicted verb still returns 200 "
            "and a full table -- every form in it is a guess."
        ),
    )
    template: str | None = Field(
        None,
        description=(
            "verbecc's internal name for the conjugation template used. "
            "Exposed because it is what a support conversation about a wrong "
            "form turns on. Passed through verbatim, including verbecc's "
            "legacy cedilla spelling, so it still matches upstream."
        ),
    )


class ConjugateResponse(BaseModel):
    input: str = Field(..., description="The request's verb, echoed verbatim.")
    notes: list[NoteOut] = Field(
        ...,
        description=(
            "Source-quality disclosures, general first. Always present. Safe "
            "to render verbatim."
        ),
    )
    verb: VerbOut
    moods: dict[str, dict[str, list[FormOut]]] = Field(
        ...,
        description=(
            "mood -> tense -> forms. A tense's array is NOT guaranteed one "
            "entry per person: where Romanian has two valid forms, both are "
            "returned with identical feats (e.g. 'a avea' present 3sg gives "
            "both 'a' and 'are')."
        ),
    )


@router.get(
    "/{verb}",
    response_model=ConjugateResponse,
    summary="Conjugate a Romanian verb",
    description=(
        "Returns the full conjugation table across seven moods: indicativ "
        "(nine tenses), conjunctiv, condi\u021bional, imperativ, infinitiv, "
        "gerunziu and participiu.\n\n"
        "Accepts the verb with or without the infinitive prefix **a** -- both "
        "`merge` and `a merge` work.\n\n"
        "Every form carries a `source`, every verb carries a `provenance`, and "
        "every response carries `notes` describing the known limits of the "
        "underlying data. See the [guide](/guide/conjugate)."
    ),
)
def get_conjugation(verb: str) -> ConjugateResponse:
    try:
        raw = conjugate_verb(verb)
    except EmptyVerbError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ConjugateResponse(**transform(raw, verb))
