# Content format

All content lives in `content/` as UTF-8 JSON. The app never needs internet to use it.
Run `python tools/validate_content.py` after every edit.

## Vocabulary — `content/vocab/*.json`

Each file is a JSON object:

```json
{
  "bank": "daily",
  "title": "Everyday German — core verbs",
  "words": [
    {
      "id": "d-verb-0001",
      "de": "gehen",
      "de_alt": [],
      "en": ["to go", "to walk"],
      "pos": "verb",
      "topic": "movement",
      "level": "A1",
      "rank": 12,
      "note": "Perfekt: ist gegangen",
      "example_de": "Ich gehe heute ins Kino.",
      "example_en": "I'm going to the cinema today."
    }
  ]
}
```

| field | required | meaning |
|---|---|---|
| `id` | yes | unique across ALL vocab files. Prefix: `d-` daily, `s-` STEM |
| `de` | yes | German headword. **Nouns always with article**: `"die Brücke"`. Verbs in infinitive. |
| `de_alt` | no | other accepted German answers (synonyms, alternate spelling), nouns with article |
| `en` | yes | list of accepted English answers; first one is shown as "the" answer. Verbs start with `to ` |
| `pos` | yes | `noun`, `verb`, `adj`, `adv`, `prep`, `conj`, `pron`, `num`, `phrase`, `other` |
| `plural` | nouns | plural with article, e.g. `"die Brücken"`; `"—"` if none |
| `topic` | yes | short lowercase tag, e.g. `food`, `school`, `physics` |
| `level` | yes | `A1`, `A2`, `B1`, `B2` (STEM words may use `B1`/`B2`) |
| `rank` | yes | integer, lower = more common/useful. New words are introduced in rank order |
| `note` | no | one short hint (irregular forms, false friends, usage) |
| `example_de` / `example_en` | yes | one short natural modern sentence + translation |

`bank` is `"daily"` (everyday), `"stem"` or `"admin"` (official German: offices, forms, paperwork; ids `a-`).
File names start with the bank (`daily_…`, `stem_…`, `admin_…`). How many new words come from each bank is set by `bank_shares` in `config.json`.

## Books — `content/books/NN_slug.json`

```json
{
  "id": "kafka-verwandlung",
  "title": "Die Verwandlung",
  "short_title": "(optional) short name for screen headers",
  "author": "Franz Kafka",
  "author_died": 1924,
  "year": 1915,
  "level": "B1-B2",
  "source": "https://... (where the German text came from)",
  "orthography": "modernised to current German spelling (dass, muss, ...); wording unchanged",
  "intro_en": "2–4 sentences: who wrote it, what it's about, why it's worth reading.",
  "units": [
    {
      "n": 1,
      "de": "Als Gregor Samsa eines Morgens aus unruhigen Träumen erwachte, ...",
      "en": "When Gregor Samsa woke one morning from troubled dreams, ...",
      "explain_en": "Plain-English explanation of what is happening and anything tricky (grammar, tone, old-fashioned words and what people say today instead). 2–5 sentences.",
      "words": [
        {"de": "erwachen", "en": "to wake up", "note": "literary; today: aufwachen"},
        {"de": "der Traum, die Träume", "en": "dream"}
      ]
    }
  ]
}
```

`author_died`, `year` and `source` are required. They are the proof that the text is public domain: the
validator refuses a book whose author died less than 70 years ago. `n` is the paragraph's permanent number
(its id is `<book id>#<n>`): never renumber, only add at the end. After any edit, run
`python tools/item_versions.py --update`.

### Story summaries (skipping parts of a long book)

To tell the whole story without translating every paragraph, put a summary unit between German units:

```json
{"n": 31, "type": "summary", "covers": "Chapters 2–4", "en": "Meanwhile: Gregor's sister starts feeding him ..."}
```

- `en`: 40–150 words of plain English retelling what happens in the skipped part, so the next German unit makes sense. Keep it suitable for 16-year-olds; mature scenes are summarised briefly and neutrally.
- No `de`, `explain_en` or `words`. Summaries are shown as "Meanwhile in the story…" and are not exercises or counted as parts.
- `n` still counts every unit (summaries included) from 1 with no gaps.

Rules for units:
- A unit is one daily lesson chunk: one paragraph, or part of a long paragraph split at sentence boundaries. Aim for **40–110 German words**; dialogue lines may be merged into one unit.
- `de` is the original text with spelling modernised (daß→dass, muß→muss, Thür→Tür, etc.). Do not change the wording.
- `en` is a faithful, natural modern English translation of exactly that unit.
- `words`: 3–8 useful words from the unit, nouns with article (+ plural when useful).
- `n` counts from 1 with no gaps.
- `sentences` (optional, used for looking back): the unit sentence by sentence, `[{"de": "...", "en": "..."}]`.
  Don't write it by hand: `python tools/sentence_pairs.py export <book> todo.json`, fill in the English,
  then `python tools/sentence_pairs.py import todo.json <book>`. If you edit a unit's `de`, delete its
  `sentences` and redo them (the validator tells you).

## Irregular verbs — `content/verbs/*.json`

```json
{"verbs": [{"inf": "gehen", "en": "to go, to walk", "past": "ging", "perfect": "ist gegangen"}]}
```

`past` is the er/sie/es form (the app works out gingst, gingen, gingt); `perfect` includes the helper
verb (`hat` or `ist`). Only verbs that appear in a paragraph the kid has read are practised, with the
book sentence as the example.
