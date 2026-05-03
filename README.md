# LexicRo API

Romanian Language Intelligence Infrastructure — open-core REST API for morphological analysis, conjugation, and lexical lookup.

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

### Lexical lookup
GET /lookup/{word}
Returns definitions from main Romanian dictionary sources (DEX '09, MDA2, DLRLC). HTML formatting is stripped from all definition text.

**Example:** `GET /lookup/casă`

```json
{
  "word": "casă",
  "definitions": [
    {
      "id": "841993",
      "source": "DEX '09",
      "text": "CASĂ1, case, s. f. 1. Clădire care servește drept locuință...",
      "modified": "2023-09-01"
    },
    {
      "id": "1048907",
      "source": "MDA2",
      "text": "casă1 sf ...",
      "modified": "2022-01-03"
    }
  ],
  "definition_count": 2
}
```

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

14 tests, all passing.

---

## Project structure
lexicro/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── routers/
│   │   ├── conjugate.py     # GET /conjugate/{verb}
│   │   └── lookup.py        # GET /lookup/{word}
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
| 1 | Conjugation + lexical lookup · Free tier | 🔨 In progress |
| 2 | Romanian BERT fine-tuning · `/analyze` morphological endpoint | Planned |
| 3 | Grammar checker · CEFR scorer · Paid tiers | Planned |
| 4 | Enterprise · On-premise packaging | Planned |

---

## Licence

Code: [MIT](LICENSE)  
Model weights (Phase 2+): CC BY-NC 4.0 — free for research and non-commercial use.

---

*Building in public. Feedback welcome at [contact@lexicro.com](mailto:contact@lexicro.com)*