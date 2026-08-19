# `/analyze` — Romanian morphological analysis

Given Romanian text, returns for every token **in context**: its lemma, part of
speech, and morphological features.

The distinction that matters is *in context*. A dictionary can tell you that
*era* is either the imperfect of **a fi** ("to be") or the definite singular of
**eră** ("era, epoch"). It cannot tell you which one you are looking at.
`/analyze` can, because a language model resolves the reading from the sentence
and the dictionary then supplies the lemma.

---

## Quick start

```bash
curl -X POST https://api.lexicro.com/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: lxr_your_key_here' \
  -d '{"text": "Elevii care s-au înscris nu vor fi afectați."}'
```

```json
{
  "model_version": "phase2-baseline-0.1",
  "truncated": false,
  "sentences": [
    {
      "tokens": [
        {
          "form": "Elevii",
          "lemma": "elev",
          "upos": "NOUN",
          "feats": {
            "Case": "Acc,Nom",
            "Definite": "Def",
            "Gender": "Masc",
            "Number": "Plur"
          },
          "source": "lexicon"
        }
      ]
    }
  ]
}
```

---

## Authentication

Pass your key in the `X-API-Key` header. Without one you get an anonymous
allowance of **10 requests/day** per IP address — enough to try the API, not
enough to build on.

Keys look like `lxr_` followed by 43 URL-safe characters. **They are shown once,
at issue time, and are not recoverable** — store yours in a password manager. If
you lose it, we revoke and reissue.

To get a key, [fill in this short form](https://tally.so/r/GxBBbz) — it takes
about a minute. You'll get a confirmation email; click the link in it and your
key is generated instantly and shown once on screen.

Didn't get the email? You can [re-send it](https://api.lexicro.com/keys/resend).

### Rate limits

| tier | requests/day |
|---|---|
| anonymous (per IP) | 10 |
| free (with key) | 1,000 |

Exceeding the limit returns **429**. For keyed requests the message names your
key's prefix (the first 12 characters), so you can quote it in support requests
without sending the key itself; anonymous requests are identified by IP.

---

## Request

```
POST /analyze
Content-Type: application/json
X-API-Key: lxr_...
```

| field | type | notes |
|---|---|---|
| `text` | string | Romanian text, 1–20,000 characters. Sentence splitting is automatic. |

Send UTF-8. Romanian diacritics (`ă â î ș ț`) must survive the round trip — if
they arrive mangled, so will the analysis.

## Response

| field | notes |
|---|---|
| `model_version` | Identifies the exact weights, lexicon and tagset used. Same input and `model_version` always produce identical output. |
| `sentences[]` | One entry per detected sentence. |
| `sentences[].tokens[]` | One entry per token, in order. |

### Token fields

| field | notes |
|---|---|
| `form` | The token as it appeared in your text. |
| `lemma` | Dictionary base form. |
| `upos` | [Universal POS tag](https://universaldependencies.org/u/pos/). |
| `feats` | [Universal Features](https://universaldependencies.org/u/feat/) — an object, empty for tokens with no morphology. |
| `source` | Where the **lemma** came from. See below. |

### The `source` field

This is provenance, not confidence, and it is genuinely useful — the three
values come from mechanisms with quite different reliability:

| value | meaning | lemma accuracy |
|---|---|---|
| `lexicon` | Exact dictionary lookup. The word is in a 352,004-form lexicon and its lemma is a fact, not a prediction. | 96.3% |
| `suffix` | Not in the lexicon; resolved by morphological suffix rules derived from that lexicon. | — |
| `model` | Not in the lexicon; predicted by the neural model. Neologisms, proper nouns, foreign words, typos. | 93.3% (combined with `suffix`) |

About 73% of tokens in ordinary text come back as `lexicon`.

**`source` is provenance, not confidence — do not use it as a trust signal.**
Punctuation, numerals and most proper nouns come back as `model` because they
are absent from the lexicon, not because the analysis is doubtful. A full stop
is `model` on every request. If you want to know whether a word was
*ambiguous*, read `candidates` below; if you want to know how much to trust a
reading, no such figure is published yet.

### The `candidates` field

Present on a token **only when the lexicon lists more than one reading** for
that form. Each entry is a `{lemma, upos, feats}` the form could have been:

```json
{
  "form": "era",
  "lemma": "fi",
  "upos": "AUX",
  "feats": {"Mood": "Ind", "Tense": "Imp", "Number": "Sing", "Person": "3"},
  "source": "lexicon",
  "candidates": [
    {"lemma": "fi",  "upos": "AUX",  "feats": {"Mood": "Ind", "Tense": "Imp"}},
    {"lemma": "eră", "upos": "NOUN", "feats": {"Case": "Acc,Nom", "Number": "Sing"}}
  ]
}
```

The reading **chosen in context** is the one in the token's own `lemma` / `upos`
/ `feats`. `candidates` is the dictionary's inventory beside it — which is
exactly why this endpoint exists rather than a dictionary lookup.

Two things to know before you rely on it:

- **The chosen reading is not guaranteed to appear in `candidates`.** The
  lexicon and the treebank disagree on annotation conventions for about 6% of
  tokens — auxiliary versus main verb, participles as adjectives, determiner
  versus pronoun — so the model legitimately returns readings the lexicon never
  offered. Treat `candidates` as "what the dictionary knows", not as a closed
  set the answer was drawn from.
- **Absence means one of two things, and `source` tells you which.**
  `source: "lexicon"` with no `candidates` means the form is in the lexicon and
  unambiguous. `source: "suffix"` or `"model"` means the form is not in the
  lexicon at all, so there is no inventory to report.

About 35.68% of tokens in running text carry a `candidates` list.

---

## Worked example: why context matters

```json
{"text": "Era obosit după drum."}
```

`Era` → lemma **`fi`**, `AUX`, `Tense=Imp` — the copula.

The same word form is also the noun *eră* ("epoch"). No lexicon can choose
between them; the choice depends on the sentence. This is the whole reason the
endpoint exists rather than a dictionary lookup.

Forms like this are not rare: **15,822 of the lexicon's 352,004 forms (4.49%)
are lemma-ambiguous** — the correct lemma genuinely depends on the reading,
which is exactly what the model resolves before the dictionary is consulted.

Romanian clitics are handled too: `s-au` is split into `s-` and `au`, and each
is analysed separately — matching the convention used by Romanian treebanks.

---

## Accuracy

Measured on the UD Romanian RRT test split (16,311 tokens, gold tokenisation):

| metric | |
|---|---|
| UPOS accuracy | 98.14% |
| Morphological features (F1) | 98.43% |
| Lemma accuracy | 95.50% |
| All three correct | 93.31% |

Sliced by dictionary coverage:

| | tokens | UPOS | lemma |
|---|---|---|---|
| in lexicon | 11,898 | 98.27% | 96.34% |
| out of lexicon | 4,413 | 97.80% | 93.25% |

Two honest caveats:

**These are gold-token evaluations** — the standard convention for Universal
Dependencies results, which is what makes them comparable to published work. The
API tokenises raw text itself, so end-to-end accuracy on arbitrary input is a
different and unmeasured quantity.

**RRT's lemmas and XPOS are automatically produced**, per the treebank's own
metadata; UPOS and features are converted with corrections. Lemma accuracy is
therefore agreement with an automatic annotation. This is the standard Romanian
benchmark, but it is not a hand-verified ceiling.

---

## Limitations

Worth knowing before you build on it:

- **This is a tagger, not a parser.** No dependency relations, no syntax tree.
- **Sentence splitting is rule-based** and will occasionally mis-split on
  unusual abbreviations. If you already have sentence boundaries, send one
  sentence per request for exact control.
- **The model never abstains.** Given a typo or an invented word it returns a
  plausible analysis rather than an error. `source` tells you when a lemma was
  predicted rather than looked up, and `candidates` shows what it was choosing
  between when the word was ambiguous.
- **Very long sentences are truncated.** If a single sentence exceeds the
  model's internal limit, the response carries `"truncated": true`. Tokens past
  the cut are still returned — so your token count matches your input — but with
  `upos: "X"` and **no `source` key**, because nothing analysed them. Send
  shorter sentences if you hit this.
- **Standard Romanian only.** Dialectal and heavily informal text is outside
  what the training data covers.
- **20,000 character limit** per request; longer text returns **413**.

---

## Errors

| status | meaning |
|---|---|
| 401 | Malformed, revoked, or inactive API key. A *missing* key is not an error — you fall back to the anonymous tier. |
| 413 | Text exceeds 20,000 characters. |
| 422 | Malformed request body. |
| 429 | Daily rate limit exceeded — the anonymous per-IP allowance, or your key's daily limit. |

---

## Attribution

Built on openly licensed resources — the MULTEXT-East Romanian lexicon and the
UD Romanian RRT treebank, both CC BY-SA 4.0, and Romanian BERT. Full citations
in [ATTRIBUTION.md](https://api.lexicro.com/attribution).
