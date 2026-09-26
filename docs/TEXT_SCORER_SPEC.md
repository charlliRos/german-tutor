# Typed-answer scorer: specification

How the tutor grades a typed word or phrase (`app/answers.py`: `check_german`, `check_english`).
Written so it can be reimplemented elsewhere, for example as a `no_std` Rust scorer with no
dependencies. **The test vectors in [`tests/vectors/text_scorer.json`](../tests/vectors/text_scorer.json) are the
contract.** An implementation is correct when it passes all of them. `tests/test_text_scorer_vectors.py` runs
them against this app.

Scorer version: `gtutor.answers/3` (the `grader` field in the answer log). Bump it when a verdict changes.
Version 2 (2026-09-25): a German noun typed in lower case is `almost`, no longer `correct`.
Version 3 (2026-09-26): English answers accept British/American spelling and contractions, and get
`almost` for the other number, one or two extra words, or another word order (step 3b, 4–5).

## Verdicts

| verdict | meaning | points (answer log) |
|---|---|---|
| `correct` | accepted | 2 of 2 |
| `almost` | right idea, small slip (umlaut, article missing, one typo) | 1 of 2 |
| `wrong` | not accepted | 0 of 2 |

Each verdict also says whether the learner may claim "my answer was right too" (`overridable`). The claim
never changes the machine verdict in the log: it is recorded next to it (`machine_verdict`, `claimed_correct`).

## Inputs

- `answer`: what was typed (any string).
- `item`: `de` (the German answer), `de_alt` (other accepted German forms), `en` (English meanings; one
  string may list alternatives with `/` or `;`), `pos` (part of speech; `noun` switches on the article rules).
- `real`: optional set of normalised forms of **every other word the app knows**. It is only used to tell a
  typo from a different word. Without it the scorer still works, but can't tell "horse" from a slip of "house".

## Step 1: normalise

Applied to both the answer and every expected form:

1. Unicode NFC, then lower case.
2. Remove each `( … )` group (hints such as `(sich) beeilen`).
3. Replace `ä→ae`, `ö→oe`, `ü→ue`, `ß→ss`.
4. Decompose (NFKD) and drop combining marks (`é→e`).
5. Delete `'`, `’`, `` ` `` and `-` (`E-Mail` = `Email`, `geht's` = `gehts`).
6. Replace every other character that is not a letter, digit or `_` with a space.
7. Collapse runs of spaces into one space and trim.

Implementation note for `no_std`: steps 1 and 4 need case and decomposition tables. For German and English
input, tables for U+0000–U+017F (Basic Latin, Latin-1 Supplement, Latin Extended-A) are enough. Characters
outside that range may be left unchanged. Declare this if you do it; no vector depends on it.

`bare(x)`: like normalise, but first map `ä→a`, `ö→o`, `ü→u`, `ß→s` (to spot a forgotten umlaut).

## Step 2: typo rule

`typo(given, expected)` is true when all of these hold:
- `expected` has at least 5 characters, and the lengths differ by at most 2;
- `0 < levenshtein(given, expected) ≤ allowed`, with `allowed = 2` if `expected` has 10 or more characters, else 1.

Levenshtein is the plain edit distance: insert, delete and substitute each cost 1 and are counted over
Unicode scalar values. A swap of two letters costs 2. Integers only, no floating point.

**A typo that is a real word is not a typo.** When the typo rule fires but the normalised answer (for German
nouns: without its article) is in `real`, the verdict is `wrong` with the message "That's a different word".

## Step 3a: German answers (`check_german`)

1. Empty after normalising → `wrong`, not overridable.
2. Equal to any normalised `de` / `de_alt` → `correct`, **unless a word that the matching candidate writes
   with a capital letter was typed in lower case** (not counting the first word, which may only be capital
   because it starts the phrase) → `almost`, "Nouns start with a capital letter in German". Compare the raw
   answer's words with the candidate's words by their normalised form.
3. For each candidate (`de`, then each `de_alt`), in order; the first rule that fires decides:
   - **Nouns with an article** (`pos = noun` and the candidate starts with der/die/das). Split the article
     off both the answer and the candidate.
     - The noun is the same (or only an umlaut is missing) or a typo, and the answer has **no article** → `almost`.
     - The noun is the same (or only an umlaut is missing) but the **article is different** → `wrong`,
       not overridable. The gender is what is being tested.
     - The umlaut is missing (`bare` forms equal) → `almost`.
     - A typo with the right article → `almost`, unless it is a real word (see step 2).
   - **Everything else:**
     - The umlaut is missing (`bare` forms equal, and the candidate has an umlaut or ß) → `almost`.
     - The candidate starts with `sich ` and the answer is the rest → `almost` (reflexive pronoun missing).
     - A typo → `almost`, unless it is a real word.
4. Otherwise → `wrong`.

## Step 3b: English answers (`check_english`)

1. Empty after normalising → `wrong`, not overridable.
2. The expected set: every meaning split on `/` and `;`, normalised, and each also without a leading
   `to `, `a `, `an ` or `the `.
3. The answer, or the answer without such a prefix, is in the expected set → `correct`.
   **The answer itself is never split on `/` or `;`**, so a list of guesses can't hit.
4. **One spelling**: both sides are put into one spelling (British → American words such as colour → color,
   `-ise`/`-isation` → `-ize`/`-ization` except words like promise, exercise, surprise; contractions spelt out:
   don't → do not). Equal now → `correct`.
5. A typo, compared **without** the prefixes on both sides (so "to do" is not a slip of "to go") → `almost`,
   unless the answer without its prefix is in `real`.
6. **Near misses** → `almost`, unless the answer adds a negation (not, no, never …) that the meaning doesn't
   have, or contains "or"/"and" (listed guesses): the same words with a regular singular/plural difference
   (dogs for dog; irregular plurals like child/children are not recognised); all the expected words plus one or
   two more; the same two or more words in another order.
7. Otherwise → `wrong`.

## What it refuses to judge

These are stated limits, not bugs:

- **Capitals are judged only on otherwise-correct German answers**, and never on the first word. A
  misspelled answer is judged by its spelling first.
- **Meanings the item doesn't list are wrong.** In the app, a German synonym from the word bank is caught by a
  separate step (`warmup._synonym_check`), and the learner can claim "my answer was right too". Both are
  recorded next to the machine verdict, never instead of it.
- **Free-text translations are not scored.** Paragraph and sentence translations are graded by the learner
  (score kind `estimated`, grader `self`, `needs_review: true`). The separate "real try" check only catches
  random, copied or pasted text. It uses floating-point similarity and is not part of this scorer.
- **Without `real`, a real word one letter away counts as a typo** (vector `en-other-word-unknown-to-bank`).

## Test vectors

`tests/vectors/text_scorer.json`: 45 cases covering `ue` for `ü`, `ss` for `ß`, a missing capital, a
missing article, a wrong article, typos, swapped letters (short and long words), a wrong-but-real word in
both languages (with a positive control each), an English word typed for German, listed guesses and
empty answers.

**Honest history:** the vectors were written in the same pass as this spec. 28 of them describe behaviour
the scorer already had, so they have never been seen failing. 3 describe the real-word rule added at the same
time (`de-real-other-word`, `en-real-other-word`, `en-sleep-for-sheep`); they were run against the
previously committed scorer and failed there, as they should. In version 2, `de-lowercase-noun` changed
from `correct` to `almost` and two capital-letter cases were added (`de-lowercase-phrase-start`,
`de-lowercase-noun-in-phrase`); the changed one and `de-lowercase-noun-in-phrase` fail against version 1. Version 3 added 12 English cases
written with the rules; the 7 that accept or soften an answer (`en-british-american`, `en-ise-ize`,
`en-contraction`, `en-other-number`, `en-extra-words`, `en-word-order`, `en-ise-exception`) fail against
version 2, the 5 that must stay wrong pass on both.
