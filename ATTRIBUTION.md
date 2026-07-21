# Attribution

LexicRo's `/analyze` endpoint is built on openly licensed language resources.
This file records what they are, how they are used, and what their licences
require. It is not legal advice; see [Open questions](#open-questions).

---

## MULTEXT-East Romanian word-form lexicon

**Used for:** lemma lookup at request time, and to derive the suffix-rule
lemmatiser for out-of-vocabulary words. Around 73% of tokens in a typical
request are resolved directly from this lexicon.

- **Resource:** MULTEXT-East free lexicons 4.0 (Romanian, `wfl-ro.txt`,
  428,194 entries)
- **Handle:** http://hdl.handle.net/11356/1041
- **Publisher:** Jožef Stefan Institute
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

> Erjavec, Tomaž et al. *MULTEXT-East free lexicons 4.0*, Slovenian language
> resource repository CLARIN.SI, 2010. http://hdl.handle.net/11356/1041

The Romanian portion derives from work by Dan Tufiș and colleagues at RACAI
(Research Institute for Artificial Intelligence "Mihai Drăgănescu", Romanian
Academy). The MULTEXT-East morphosyntactic specification defines the MSD tagset
that LexicRo's MSD→UD bridge converts.

---

## UD Romanian RRT (RoRefTrees)

**Used for:** training and evaluating the morphological tagger and the lemma
head. Every accuracy figure LexicRo publishes is measured on this treebank's
test split.

- **Resource:** UD_Romanian-RRT, Universal Dependencies
- **Repository:** https://github.com/UniversalDependencies/UD_Romanian-RRT
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **Contributors:** Barbu Mititelu, Verginica; Irimia, Elena; Perez,
  Cenel-Augusto; Ion, Radu; Simionescu, Radu; Popel, Martin
- **Contact:** vergi@racai.ro

> Barbu Mititelu, Verginica, Radu Ion, Radu Simionescu, Elena Irimia and
> Cenel-Augusto Perez. *The Romanian Treebank Annotated According to Universal
> Dependencies.* Proceedings of the Tenth International Conference on Natural
> Language Processing (HrTAL 2016).

Built on RACAI-RoTb (Irimia and Barbu Mititelu, 2015) and UAIC-RoTb (Perez,
2014). Development supported by CNCS-UEFISCDI project PN-II-RU-TE-2014-4-1362
and COST action CA21167 UniDive.

**Annotation provenance**, per the treebank's own metadata: lemmas and XPOS are
*automatic*; UPOS and features are *converted with corrections*; dependency
relations are *manual native*. LexicRo's reported lemma accuracy is therefore
agreement with an automatic annotation, and the MSD→UD bridge validation is
agreement between two converters. This is the standard benchmark for Romanian
and the figures are comparable to published work, but the distinction is worth
stating rather than glossing.

---

## Romanian BERT

**Used for:** the contextual encoder that disambiguates readings a lexicon
cannot resolve alone.

- **Model:** `dumitrescustefan/bert-base-romanian-cased-v1`
- **Source:** https://huggingface.co/dumitrescustefan/bert-base-romanian-cased-v1

> Dumitrescu, Stefan Daniel, Andrei-Marius Avram and Sampo Pyysalo. *The Birth
> of Romanian BERT.* Findings of EMNLP 2020. https://arxiv.org/abs/2009.08712

---

## Universal Dependencies

The UPOS tags and morphological features returned by `/analyze` follow the
[Universal Dependencies](https://universaldependencies.org/) v2 guidelines.

---

## Open questions

Both CC BY-SA 4.0 resources carry a ShareAlike condition, and the two are used
differently:

- the **lexicon** is redistributed as data inside the deployed artifact;
- the **treebank** was used to train model weights that are not themselves
  distributed, but which the service exposes through an API.

Whether either use produces "adapted material" that triggers ShareAlike — and
what that would require of a commercial service — is a genuine question rather
than a settled one, and it is being clarified with the rights holders. Nothing
here should be read as a determination either way.

Attribution as required by both licences is given above.
