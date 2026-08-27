# `/conjugate` — Romanian verb conjugation

Given a Romanian verb, returns its full conjugation table: seven moods, every
tense in each, every person and number that mood takes.

---

## Quick start

```bash
curl https://api.lexicro.com/conjugate/merge \
  -H 'X-API-Key: lxr_your_key_here'
```

The `a` prefix is optional — `/conjugate/merge` and `/conjugate/a%20merge`
return identical `moods`, differing only in the `input` field that echoes
what you sent.

The response is long (nine indicative tenses alone), so here is a trimmed
excerpt showing the shape:

```json
{
  "input": "merge",
  "notes": [
    {
      "scope": "all",
      "code": "upstream_unverified",
      "message": "Forms come from verbecc 2.0.3 and are not exhaustively verified. ..."
    },
    {
      "scope": "imperativ",
      "code": "imperative_known_errors",
      "message": "The imperative has known residual errors in a small set of verbs ..."
    }
  ],
  "verb": {
    "infinitive": "merge",
    "provenance": "template",
    "template": "concu:rge"
  },
  "moods": {
    "indicativ": {
      "prezent": [
        {"form": "merg", "pronoun": "eu", "feats": {"Person": "1", "Number": "Sing"}, "source": "verbecc"},
        {"form": "mergi", "pronoun": "tu", "feats": {"Person": "2", "Number": "Sing"}, "source": "verbecc"}
      ]
    },
    "condițional": {
      "prezent": [
        {"form": "aș merge", "pronoun": "eu", "feats": {"Person": "1", "Number": "Sing"}, "source": "derived"}
      ]
    }
  }
}
```

---

## Authentication

Pass your key in the `X-API-Key` header. Without one you get an anonymous
allowance of **10 requests/day** per IP address. See
[the `/analyze` guide](/guide) for how to get a key — both endpoints share one
key and one daily quota.

---

## Response

| field | type | notes |
|---|---|---|
| `input` | string | The verb you requested, echoed verbatim — with the `a` prefix if you sent it. |
| `notes` | array | Source-quality disclosures, always present, general first. Safe to render verbatim. Each entry has a `scope` (`"all"`, or a mood name), a stable `code` you may rely on, and a `message` whose wording may be revised. The `imperative_known_errors` entry also carries **`verbs`** — the lemmas it is about — and `paradigm_contradiction` carries **`tenses`**, the `mood/tense` pairs it is about, so you can flag the affected forms without parsing the message. See [Known limitations](#known-limitations). |
| `verb.infinitive` | string | The verb as looked up, without the `a` prefix. |
| `verb.provenance` | `"template"` \| `"predicted"` | Whether the conjugation library recognised this verb. See [below](#two-kinds-of-provenance). |
| `verb.template` | string \| null | The library's internal name for the conjugation pattern used. Kept for support conversations about a specific wrong form — see [Diacritics](#diacritics) for why its spelling is the one exception to comma-below. |
| `moods` | object | `mood → tense → array of forms`. See the mood table below, and [A tense is not one form per person](#a-tense-is-not-one-form-per-person). |

Each entry in a tense's array has:

| field | type | notes |
|---|---|---|
| `form` | string | The inflected form, without its pronoun. The literal string `"-"` means the form does not exist for that person — verbecc's own sentinel, passed through rather than hidden. Impersonal verbs are the usual reason: *a ninge* ("to snow") has no imperative, so its `imperativ` entries read `"-"`. In the **synthesised `condițional`** there is no verbecc value to pass through, so `"-"` is **mirrored from the same person's `indicativ.prezent`**: *a ninge* has a third-person singular and nothing else, so only that person carries a conditional. Mirroring is per person, not per verb — *a ninge* has a 3sg but no 3pl. |
| `pronoun` | string \| null | The pronoun this form takes (`eu`, `tu`, `el`, `ea`, `noi`, `voi`, `ei`, `ele`), or `null` for moods that take none — `infinitiv`, `gerunziu`, `participiu`. Present and `null`, not omitted, so you can rely on the key existing. |
| `feats` | object | [Universal Features](https://universaldependencies.org/u/feat/), the same vocabulary `/analyze` uses: `Person` (`"1"`\|`"2"`\|`"3"`), `Number` (`"Sing"`\|`"Plur"`), and `Gender` (`"Masc"`\|`"Fem"`) on third person only. A feature that doesn't apply is absent from the object, not present with a null value. |
| `source` | `"verbecc"` \| `"derived"` | Which system produced this specific form. See [below](#two-kinds-of-provenance). |

---

## The seven moods

| Mood | Tenses | Source |
|---|---|---|
| `indicativ` | prezent, imperfect, perfect-simplu, perfect-compus, mai-mult-ca-perfect, viitor-1, viitor-1-popular, viitor-2, viitor-2-popular | verbecc |
| `conjunctiv` | prezent, perfect | verbecc |
| `condițional` | prezent, perfect | derived by LexicRo |
| `imperativ` | imperativ, negativ | verbecc, filtered to 2sg/2pl |
| `infinitiv` | afirmativ | verbecc |
| `gerunziu` | gerunziu | verbecc |
| `participiu` | participiu | verbecc |

`/conjugate` is built on [verbecc](https://pypi.org/project/verbecc/), an
open-source Romanian conjugation library. Most forms pass through from it
unchanged. Two things don't, and both matter enough to call out on their own.

**`condițional` is composed by LexicRo, not verbecc.** The library declares
this mood but ships no data for it. Romanian's conditional auxiliary (`aș`,
`ai`, `ar`, `am`, `ați`, `ar`) is invariant — it doesn't change with the verb
— so LexicRo builds `prezent` as auxiliary + infinitive and `perfect` as
auxiliary + `fi` + participle, using verbecc's own infinitive and participle
as the base. Every form in this mood carries `source: "derived"`.

**The negative imperative's 2sg form is also composed, for the same reason.**
Romanian's negative imperative singular is invariantly `nu` + the infinitive
— there's no verb where it legitimately differs from that pattern — so
LexicRo builds it the same way it builds the conditional: apply the paradigm
rather than trust a per-verb library entry. That form carries
`source: "derived"` too. The 2pl negative imperative is a different pattern
(`nu` + the plural imperative form, not `nu` + infinitive) and comes from
verbecc as `source: "verbecc"` like everything else in the mood — so within
one `imperativ.negativ` array you'll see both sources side by side:

```json
"negativ": [
  {"form": "nu merge",   "pronoun": "tu",  "source": "derived"},
  {"form": "nu mergeți", "pronoun": "voi", "source": "verbecc"}
]
```

That's not an inconsistency to debug — it's two different rules for two
different persons, disclosed via `source` so you don't have to guess which
applied.

---

## Two kinds of provenance

`verb.provenance` and `form.source` answer different questions:

- **`verb.provenance`** — did the library recognise this verb at all?
  `"template"` means it matched a known conjugation pattern. `"predicted"`
  means it didn't, and guessed a pattern from the verb's ending instead.
- **`form.source`** — which system produced *this particular form*,
  `"verbecc"` or `"derived"` (see above).

An unrecognised verb still returns **200**, not 404 — a made-up or
unfamiliar verb usually still conjugates the way Romanian verbs of its shape
do, and that guess is often useful. `verb.provenance` is how you know it was
a guess:

```bash
curl https://api.lexicro.com/conjugate/xyzzyti \
  -H 'X-API-Key: lxr_your_key_here'
```

```json
{
  "infinitive": "xyzzyti",
  "provenance": "predicted",
  "template": "fer:i"
}
```

When `provenance` is `"predicted"`, every form in the response is a guess —
not just the ones marked `derived`. Only genuinely unrecognisable input (not
a plausible Romanian verb at all) returns 404; see [Errors](#errors).

---

## Known limitations

Forms come from verbecc and are not exhaustively verified, and this applies
across the whole response rather than to one mood. Two defects outside the
imperative — the indicative present of *a minți*, which returned `eu mit`
for `eu mint`, and the infinitive of *a face*, which returned a corrupted
Spanish string — were reported upstream and corrected in verbecc 2.0.3.
Both were found by spot check rather than by an audit, and the data has not
been audited as a whole, so treat the absence of a current example as
telling you nothing.

The imperative has its own, narrower set of known issues on top of that.
Three verbs — *a merge*, *a trece* and *a tăcea* — are served their third
person singular where a second person imperative belongs, so *merge*
returns `merge` where correct Romanian is `mergi`. Separately, for some
verbs the correct imperative form depends on whether the verb is used
transitively — `treci!` versus `trece-mă!` — and a bare verb name doesn't
tell you which sense was meant, so the returned form may not be the one your
context needs.

The three verbs are also listed in that note's `verbs` field, so you can mark
the affected forms in your own interface rather than relying on a reader
noticing a caveat elsewhere on the page. **Do not try to detect them from the
shape of the data instead** — the defect's signature, a second-person singular
imperative identical to the third-person singular present, is equally true of
*a cânta* (`cântă`) and *a găsi* (`găsește`), which are perfectly correct.
The set is enumerated because it cannot be computed.

When the upstream fix lands, the list shrinks and this note eventually goes.

### When a verb's paradigm contradicts itself

Some verbs mark persons as having no form in the present tense while other tenses supply forms
for those same persons. *A ninge* ("to snow") gives `-` for every person but the third singular
in `indicativ prezent`, then returns `eu am nins` in `indicativ perfect-compus`.

When that happens the response carries a `paradigm_contradiction` note, listing the affected
`mood/tense` pairs in its `tenses` field. It is computed per response, so it appears only on
verbs that actually exhibit it.

**The note does not tell you which side is wrong, because we do not know.** Both readings occur
among the affected verbs: *a curge* really is third-person-only, so its `eu am curs` is the
error — while *a aporta* is an ordinary transitive verb wrongly marked third-person-only, so
there the *present* is the error and `eu am aportat` is correct. A caller who needs to choose
must do so per verb; a caller who only needs to warn a user can render the note.

These are reported upstream to the library maintainers. LexicRo relays the
forms verbecc produces rather than substituting its own corrections, so
every value in a response is traceable to one source — the alternative,
silently fixing what looks wrong, would leave you unable to tell which forms
were verified and which were guessed at by whoever wrote the fix.

The `notes` field in every response carries this same disclosure in
machine-readable form — `code: "upstream_unverified"` for the general case,
`code: "imperative_known_errors"` for the imperative — so you can surface it
to your own users without hardcoding this page's wording.

---

## A tense is not one form per person

Most tenses return exactly one entry per person/number combination — eight
entries for a fully personal tense (`eu`, `tu`, `el`, `ea`, `noi`, `voi`,
`ei`, `ele`). Some don't. Where Romanian genuinely has two valid forms for
one person, both come back as separate entries with identical `feats`.

The clearest example is *a avea*, present tense, third person singular:

```json
[
  {"form": "a",   "pronoun": "el", "feats": {"Person": "3", "Number": "Sing", "Gender": "Masc"}, "source": "verbecc"},
  {"form": "are", "pronoun": "el", "feats": {"Person": "3", "Number": "Sing", "Gender": "Masc"}, "source": "verbecc"}
]
```

`a` (the short auxiliary form, as in *el a mâncat*) and `are` (the full main
verb, as in *el are un câine*) are both correct third-person-singular present
forms of *a avea*. Neither is more correct than the other, so both are
returned rather than picking one. If your code indexes into a tense's array
by position expecting one entry per person, it will silently pick up
whichever of these it happens to land on — check the array length, or match
on `pronoun` and `feats` and expect more than one hit.

---

## Diacritics

Every field in the response uses Romanian's comma-below diacritics — `ș`
(U+0219) and `ț` (U+021B) — matching `/analyze`. The one exception is
`verb.template`: it is verbecc's own internal identifier, passed through
exactly as the library spells it (including its legacy cedilla `ş`/`ţ`
characters where present), because it's what you'd quote back to us — or to
verbecc — in a bug report about a specific form.

---

## Errors

| status | meaning |
|---|---|
| 200 | Success — including a `"predicted"` verb. See [Two kinds of provenance](#two-kinds-of-provenance). |
| 400 | Blank or whitespace-only verb. |
| 401 | Malformed, revoked, or inactive API key. A *missing* key is not an error — you fall back to the anonymous tier. |
| 404 | The input isn't a recognisable Romanian verb at all. |
| 429 | Daily rate limit exceeded. |

---

## Attribution

Conjugation is generated by [verbecc](https://pypi.org/project/verbecc/).
Full citations in [`/attribution`](https://api.lexicro.com/attribution).
