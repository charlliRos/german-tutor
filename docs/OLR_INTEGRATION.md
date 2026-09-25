# Working with the Open Learning Runtime

The Open Learning Runtime (OLR) is the family's learning platform (a separate, private project). It has three
ways to integrate. **This app takes route C, "keep your runtime":** the tutor stays a Python terminal app with
its own scheduler, speech and duels. It exchanges data in OLR's shapes. Nothing of ours runs inside OLR's
sandbox, so there is no rewrite and no 16 MiB / WASM limit.

Status on both sides (September 2026): OLR's protocol and grader are built. Its **content package format
(signed manifest, digest, scope certificate) is designed, not built.** So nothing here targets a finished
format. What is done is the permanent groundwork, plus a throwaway exporter that shows the mapping.

## What is in place

| OLR asks for | Here | Where |
|---|---|---|
| Permanent, opaque item ids | Every word (`d-noun-0001`), verb form (`gehen\|past`) and paragraph (`kafka-verwandlung#12`) | content files; paragraph ids are `book id # Unit.n` |
| Versions, and which edit changed what | `content/item_versions.json`: version per item, and each edit's tier: **answer**, **wording** or **presentation** | `app/versions.py`, `tools/item_versions.py` |
| Paragraphs never renumbered | A paragraph whose text becomes a different paragraph is refused | `validate_content.py`, `tests/test_content_versions.py` |
| Append-only attempt events, progress derived | Every graded answer goes to `data/profiles/<name>_attempts.jsonl`. `attempts.rebuild()` recomputes the word, verb and gender boxes from the log alone | `app/attempts.py`, `tests/test_attempts.py` |
| Self-graded kept apart from machine-graded | Score kinds `dichotomous`, `polytomous`, `estimated` (self: `confidence 0.5`, `needs_review`), `no_response`; `grader` on every event; a "my answer was right too" claim is kept next to the machine verdict, never instead of it | `app/attempts.py` |
| Competencies | 12 competencies with subcompetencies (word list/topic, ending rule, verb tense, book) | `attempts.COMPETENCIES`, below |
| Provenance per text | Author's death, first publication, source edition, spelling changes, and the public-domain reason worked out from them | book files, `export_olr.rights()` |
| A text scorer (OLR has none) | Written spec + 33 test vectors, integer-only, no locale behaviour | [`TEXT_SCORER_SPEC.md`](TEXT_SCORER_SPEC.md), `tests/vectors/text_scorer.json` |

## Content rules for whoever edits content/

1. **Never change an id, never reuse one.** A removed word stays in `item_versions.json` as retired.
2. **Never renumber paragraphs.** Add new paragraphs at the end of a book, or in a new book.
3. After every content edit: `python tools/item_versions.py --update`, then `python tools/validate_content.py`.
   The tests fail if the versions file is out of date.
4. OLR's rule is stricter than ours: there, changing an answer **mints a new id**. Here the id stays and the
   version goes up with tier `answer`. An exporter that needs OLR's rule can form `id~v3` from the log.

## The exporter (throwaway)

```
python tools/export_olr.py                   # content: export/olr/
python tools/export_olr.py --attempts Anna   # plus Anna's answer log (what she typed: private)
```

It writes `manifest.json` (`format_version: 0`), `items.jsonl`, `books.jsonl`, `competencies.json` and
`attempts/<name>.jsonl`:

- Per word: `.en2de` and `.de2en` text questions. For nouns with one gender, also a `.gender` question as
  `choice_single` with OLR's built `exact_option` scorer.
- Per verb: `|past` and `|perfect` text questions.
- Per paragraph: the text, reference translation, explanation, key words, and two translation tasks with
  score kind `estimated` / grader `self`.
- Answers: OLR's closed score union (`Dichotomous`, `Polytomous`, `Estimated`), with
  `machine_verdict` / `claimed_correct` when the learner overrode the machine.
- **"Didn't answer" is left unmapped** (`score: null` plus an `unmapped` reason). OLR's `Dichotomous` has no
  such state, and our items aren't option-based, so `Polytomous`'s `chosen: None` doesn't fit either. Turning it
  into "wrong" would lose the difference between "didn't try" and "tried and was wrong". This is OLR's open
  question NQ-K2-UNANSWERED-VS-WRONG; our log keeps `no_response` as its own kind.

Throw it away when OLR's package format (their node CP1) exists. The ids, versions, log and spec it reads
from are the permanent part.

## Competencies

| id | what it practises | subcompetency |
|---|---|---|
| `vocabulary.production` | German word from the English (typed) | word list / topic |
| `vocabulary.recognition` | English meaning of a German word (typed) | word list / topic |
| `vocabulary.in_context` | the right form in the word's example sentence (gap) | word list / topic |
| `listening.dictation` | hear a sentence, type it | word list / topic, or book |
| `speaking.pronunciation` | say it so the speech checker hears it | word list / topic, or book |
| `grammar.noun_gender` | der / die / das | ending rule (`-ung`, `-chen`, …) or `no-rule` |
| `grammar.case_articles` | the article form the case needs | `article` |
| `grammar.adjective_endings` | adjective endings | `ending` |
| `grammar.word_order` | German word order | `order` |
| `grammar.irregular_verbs` | past tense and perfect | `past` / `perfect` |
| `reading.translation_de_en` | German text → English | book |
| `writing.translation_en_de` | English text → German | book |

## Not done, on purpose

These are open or unbuilt on OLR's side. Building one side of them now would be guessing:

- **Signing, digests, scope certificates, package manifests**: OLR's CP1 is not built.
- **Speaking and listening as OLR capabilities** (`audio.tts`, `audio.listen`): open there. Here they stay
  optional: every exercise works without a microphone.
- **Learner identity, classes, guardians**: OLR's kids product has no deployment and no roster model yet.
  The log uses the profile name.
- **Licence**: OLR's content licence terms are open, and **this repository has no licence yet**. The
  German texts are public domain; the English translations, explanations and word entries were written for
  this app. A licence for those has to be chosen before anyone signs a package.

## Rights of the texts (checked by the exporter)

Which rule applies depends on **where a package is distributed**, not where the author lived; each book's
`rights.computed_for` says which countries were checked. All 10 books are public domain under "author's life + 70 years" (Germany, Austria, Switzerland, the EU and
Indonesia). Four are still protected in the **United States** (95 years after publication): Borchert (until
2043), Horváth (2033), Tucholsky (2027) and Zweig (2038). That matters only if a package is distributed there.
`validate_content.py` refuses a book whose author died less than 70 years ago.
