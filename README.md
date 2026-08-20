# LexicRo API

Romanian Language Intelligence Infrastructure — open-core REST API for Romanian morphological analysis and verb conjugation.

**Status:** Phase 1 in active development · [lexicro.com](https://lexicro.com) · [contact@lexicro.com](mailto:contact@lexicro.com)

---

## Endpoints

### Health check

```
GET /health
```

```json
{"status": "ok", "version": "0.1.0"}
```

---

### Verb conjugation
GET /conjugate/{verb}
Accepts the verb with or without the Romanian infinitive prefix — both `merge` and `a merge` are valid.

Returns the full conjugation table across all moods and tenses, including perfect simplu and viitor I.

**Example:** `GET /conjugate/merge`

```json
{
  "moods": {
    "indicativ": {
      "prezent": [
        {"c": ["eu merg"], "n": "s", "p": "1", "pr": "eu"},
        {"c": ["tu mergi"], "n": "s", "p": "2", "pr": "tu"},
        ...
      ],
      "perfect-simplu": [...],
      "viitor-1": [...]
    },
    "conjunctiv": {...},
    "imperativ": {...},
    "gerunziu": {...},
    "participiu": {...}
  },
  "verb": {
    "infinitive": "merge",
    "predicted": false,
    "template": "concu:rge"
  }
}
```

`"predicted": false` means the verb was found in the known verb database. `"predicted": true` means the conjugation was inferred by the ML model.

---

### Morphological analysis

```
POST /analyze
```

Returns lemma, part of speech and morphological features for every token **in
context** — the reading a dictionary alone cannot resolve.

Full documentation: [docs/analyze.md](docs/analyze.md) · live at
[api.lexicro.com/guide](https://api.lexicro.com/guide).

---

## Temporarily unavailable

`GET /lookup/{word}`, `GET /inflect/{word}` and `POST /difficulty` are
**disabled** and are not served by the API.

These three are backed by DEXonline data, and are withdrawn pending a permission
decision on that source. The route handlers remain in the tree but are not
registered in `app/main.py`. They will be documented here again if and when they
return — treat any older description of them as out of date.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the data sources currently in use.

---

## Running locally

**Requirements:** Python 3.13+

```bash
git clone https://github.com/LexicRo/lexicro.git
cd lexicro
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Interactive docs available at `http://127.0.0.1:8001/docs`.

---

## Running tests

```bash
pytest tests/ -v
```

26 tests, all passing.

---

## Project structure
lexicro/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── routers/
│   │   ├── conjugate.py     # GET /conjugate/{verb}
│   │   ├── analyze.py       # POST /analyze
│   │   └── lookup.py        # GET /lookup/{word}  (not registered)
│   ├── services/
│   │   ├── verbecc_service.py   # verbecc wrapper
│   │   └── dex_service.py       # DEXonline wrapper
│   └── models/              # Pydantic models (Phase 2)
├── tests/
│   ├── test_conjugate.py    # 7 tests
│   └── test_lookup.py       # 7 tests
├── requirements.txt
└── LICENSE                  # MIT

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
|       |       |        |
| 1 | Conjugation · Free tier | 🔨 In progress — lookup / inflection / validation withdrawn, see above |
| 2 | Romanian BERT fine-tuning · `/analyze` morphological endpoint | ✅ Live |
| 3 | Grammar checker · CEFR scorer · Paid tiers | Planned |
| 4 | Enterprise · On-premise packaging | Planned |

---

## Live API

Base URL: `https://api.lexicro.com`

Interactive docs: `https://api.lexicro.com/docs`

---

## Licence

**Code: [MIT](LICENSE)** — both the API service and the `lexicro-nlp`
morphological engine.

**Model weights: not currently distributed.** They are trained on CC BY-SA 4.0
material, and their licence terms are still being settled with the rights
holders. This page previously stated CC BY-NC 4.0; that was withdrawn in July
2026, because CC BY-NC is not compatible with the ShareAlike terms of the
training data. Nothing has replaced it yet, and saying so is more useful than
naming a licence that would not hold.

In practice: you can read, fork and build on the code today, but standing up
your own instance means training your own model.

Attribution for the underlying language resources is in
[ATTRIBUTION.md](ATTRIBUTION.md).

---

*Building in public. Feedback welcome at [contact@lexicro.com](mailto:contact@lexicro.com)*