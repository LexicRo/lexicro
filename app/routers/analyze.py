"""POST /analyze -- morphological analysis.

Drop this in as `app/routers/analyze.py` alongside the Phase 1 routers. It
follows the same conventions: an APIRouter with a tag, rate limiting applied by
`main.py` via the shared `dependencies` list, and Pydantic models so the
OpenAPI spec and Swagger UI document themselves.

The Analyzer is a module-level singleton created at import time, NOT per
request: the model plus a 352k-form lexicon take seconds to load and hundreds of
MB of RAM. Building that per request would make the endpoint unusable.

Inference is synchronous and CPU-bound, so the handler is declared `def`, not
`async def`. FastAPI then runs it in its threadpool, and one slow request cannot
block the event loop for everyone else. Declaring it `async def` would be a
quiet way to serialise the whole service behind a single tokenisation.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from lexicro_nlp.analyzer import Analyzer

router = APIRouter(prefix="", tags=["Analysis"])

MODEL_DIR = os.environ.get("LEXICRO_MODEL_DIR", "/models/analyze-v1")


@lru_cache(maxsize=1)
def get_analyzer() -> Analyzer:
    """Loaded once per worker process, on first use."""
    return Analyzer(MODEL_DIR)


class AnalyzeRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        description="Romanian text to analyse. Sentence splitting is automatic.",
        json_schema_extra={"example": "Elevii care s-au înscris nu vor fi afectați."},
    )


class TokenOut(BaseModel):
    form: str = Field(..., description="The token as it appeared in the text")
    lemma: str = Field(..., description="Dictionary base form")
    upos: str = Field(..., description="Universal POS tag (NOUN, VERB, ADJ, ...)")
    feats: dict[str, str] = Field(
        default_factory=dict,
        description="Universal Features: Case, Number, Gender, Person, Tense, Mood, ...",
    )
    source: str = Field(
        ...,
        description="Where the lemma came from: 'lexicon' (exact lookup) or "
                    "'model' (predicted for an out-of-vocabulary word)",
    )


class SentenceOut(BaseModel):
    tokens: list[TokenOut]


class AnalyzeResponse(BaseModel):
    model_version: str = Field(
        ...,
        description="Frozen weights + lexicon + tagset. Identical input and "
                    "model_version always yield identical output.",
    )
    sentences: list[SentenceOut]


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Morphological analysis of Romanian text",
    description=(
        "Returns, for every token in context: its lemma, part of speech, and "
        "morphological features (case, number, gender, person, tense, mood, ...).\n\n"
        "Disambiguation is contextual. A lexicon alone cannot tell you that *era* "
        "is an auxiliary in one sentence and a main verb in another; this endpoint "
        "can, because a language model resolves the reading from context and the "
        "lexicon supplies the lemma."
    ),
)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    analyzer = get_analyzer()
    try:
        sentences = analyzer.analyze(req.text)
    except ValueError as exc:                      # text too long
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return AnalyzeResponse(
        model_version=analyzer.model_version,
        sentences=[
            SentenceOut(tokens=[TokenOut(**t.to_dict()) for t in sent])
            for sent in sentences
        ],
    )


@router.get(
    "/analyze/info",
    summary="Model metadata",
    description="Version, tagset size and lexicon coverage of the deployed model.",
)
def analyze_info() -> dict:
    return get_analyzer().info()
