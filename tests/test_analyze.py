"""/analyze response-contract tests (ADR-0022).

The real Analyzer loads a ~500MB model, so these swap in a fake. They test the
CONTRACT -- which keys appear when -- not the linguistics.
"""

import pytest
from fastapi.testclient import TestClient

from lexicro_nlp.analyzer import Analysis, Token

import app.routers.analyze as analyze_mod
from app.main import app
from app.middleware.rate_limit import check_rate_limit

client = TestClient(app)

# Schema-contract tests assert the SHAPE of the response. The rate limiter
# queries Postgres on every route, which would make these tests depend on a
# migrated database to check a JSON key. Stub it out: limiter behaviour is
# not what these tests are for.
app.dependency_overrides[check_rate_limit] = lambda: None


class FakeAnalyzer:
    model_version = "test-0.0"

    def __init__(self, analysis):
        self._analysis = analysis

    def analyze(self, text):
        return self._analysis


@pytest.fixture
def fake(monkeypatch):
    def install(analysis):
        monkeypatch.setattr(
            analyze_mod, "get_analyzer", lambda: FakeAnalyzer(analysis)
        )
    return install


def test_unambiguous_token_has_source_and_no_candidates(fake):
    fake(Analysis(sentences=[[Token("casă", "casă", "NOUN", {"Number": "Sing"}, "lexicon")]]))
    r = client.post("/analyze", json={"text": "casă"})
    assert r.status_code == 200
    tok = r.json()["sentences"][0]["tokens"][0]
    assert tok["source"] == "lexicon"
    assert tok.get("candidates") is None


def test_ambiguous_token_carries_candidates(fake):
    cands = [
        {"lemma": "fi", "upos": "AUX", "feats": {"Tense": "Imp"}},
        {"lemma": "eră", "upos": "NOUN", "feats": {"Number": "Sing"}},
    ]
    fake(Analysis(sentences=[[Token("era", "fi", "AUX", {"Tense": "Imp"}, "lexicon", cands)]]))
    r = client.post("/analyze", json={"text": "era"})
    tok = r.json()["sentences"][0]["tokens"][0]
    assert len(tok["candidates"]) == 2
    assert {c["lemma"] for c in tok["candidates"]} == {"fi", "eră"}
    # the chosen reading still lives in the token body itself
    assert tok["lemma"] == "fi"


def test_truncated_token_omits_source_key(fake):
    fake(Analysis(sentences=[[Token("cuvântul", "cuvântul", "X", {})]], truncated=True))
    r = client.post("/analyze", json={"text": "cuvântul"})
    body = r.json()
    assert body["truncated"] is True
    tok = body["sentences"][0]["tokens"][0]
    # ADR-0022: the key is ABSENT, not null. Without
    # response_model_exclude_none=True this is '"source": null' and the
    # published guide would be wrong.
    assert "source" not in tok
    assert tok["upos"] == "X"


def test_truncated_defaults_false(fake):
    fake(Analysis(sentences=[[Token("casă", "casă", "NOUN", {}, "lexicon")]]))
    r = client.post("/analyze", json={"text": "casă"})
    assert r.json()["truncated"] is False


def test_openapi_documents_all_three_source_values():
    schema = client.get("/openapi.json").json()
    desc = schema["components"]["schemas"]["TokenOut"]["properties"]["source"]["description"]
    for value in ("lexicon", "suffix", "model"):
        assert value in desc
    assert "truncated" not in desc


def test_openapi_exposes_candidates():
    schema = client.get("/openapi.json").json()
    assert "candidates" in schema["components"]["schemas"]["TokenOut"]["properties"]
    assert "CandidateOut" in schema["components"]["schemas"]
