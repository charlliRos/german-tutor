# Learning design: the loop and the skill graph

How "Deutsch mit Fritz & Pip" should make German stick, from where the app is today (September 2026) to
Goethe A2 → B1 (to work in Germany) and later C1. This is a design, not code. It keeps the answer log, the
item ids and the Leitner boxes, and every step at the end ships on its own.

Sections: 1 What we have and what the science says · 2 The learning loop (day, week, term) · 3 Placement,
adaptation, leeches · 4 Exam practice in the loop · 5 The skill graph · 6 Data and export · 7 Build plan.

---

## 1. Starting point

What the app already does well, in learning-science terms:

| Principle | Already in the app |
|---|---|
| Retrieval practice (recall beats re-reading) | Every word is typed, both directions; gap fills; dictation |
| Spacing | Leitner boxes 1/3/7/16/35 days for words, verbs, genders; the same ladder for paragraphs |
| Feedback right away | Scorer says right / almost / wrong with a message; misses repeat until right |
| Varied cues | Word, gap in the example sentence, dictation, speaking turn |
| Relatedness | Duels, async challenges, "Ben just finished…" |
| Honest record | Append-only log, self-grades kept apart from machine grades |

What the science says is missing, and what this design adds:

| Gap (from this week's review) | Principle | Fix (section) |
|---|---|---|
| Warm-up grows by date; 60-minute sessions | Session length; attention; drop-out | Minutes budget, priority order, end on a success (2.1) |
| No placement | Desirable difficulty means *calibrated* difficulty | 15-minute placement seeds the boxes (3.1) |
| Books from day 1, near C1 | Comprehensible input at 95–98% known words | Coverage gate; graded readers A2/B1 (2.3, 7 step 9) |
| 40% of new words STEM/admin | Motivation: relevance for teens | Level cap and teen tracks (3.2) |
| Self-grading has no cost | Feedback must be able to say "no" | "Prove it" check after a self-grade (2.4) |
| Speaking turn shows the answer | Retrieval, not reading aloud | Say before you see (2.2) |
| No leech handling | Some items need a different cue, not more of the same | Leech ladder (3.4) |
| Top interval 35 days | Spacing needs long intervals for 8,400 words | Boxes 6 and 7: 75 and 150 days (3.3) |
| No capital letters | German orthography is tested in every exam | Capitals count (3.5) |
| Nothing ties skills to CEFR/exams | Goals and competence feedback for teens | Skill graph, readiness, mock exams (4, 5) |

Content facts that shape the design: 6,720 everyday words (A1 814, A2 1,490, B1 2,525, B2 1,698, C1 193),
419 STEM, 162 official. All ten books are B1–B2 or harder; the easiest (Borchert) is A2–B1. So an A2 kid
knows ~1,000–1,500 words and the nearest text needs ~3,000. That gap is the biggest single problem.

---

## 2. The learning loop

### 2.1 A day (school day: 20–25 minutes; weekend: up to 40)

```
 check-in    reviews due      new words        input           output        wrap-up
 (1 min)     (8-12 min)       (3-6 min)        (5-8 min)       (3-5 min)     (1 min)
+--------+  +-------------+  +------------+  +-------------+  +----------+  +----------+
| streak |  | words, verbs|  | <= N cards |  | text at     |  | write 2-3|  | what you |
| plan   |->| genders,    |->| retrieval  |->| 95-98% known|->| sentences|->| learned, |
| goal   |  | grammar     |  | after 3-5  |  | words, then |  | or say 1 |  | what's   |
|        |  | interleaved |  | items later|  | look backs  |  | check    |  | back     |
+--------+  +-------------+  +------------+  +-------------+  +----------+  | tomorrow |
      ^         misses ---> "again until it sticks" (at the end, as today)   +----------+
      |                                                                          |
      +-------------------- tomorrow's plan is derived from today's log ---------+
```

| Step | What the kid does | Why it sticks |
|---|---|---|
| Check-in | Sees streak, today's plan ("38 to review, 6 new, one text"), picks the day's goal if the plan is over budget ("do reviews only") | Autonomy and a clear end point; teens drop out of open-ended sessions |
| Reviews due | Typed recall as now, but words, verb forms, der/die/das and grammar are **shuffled into one queue** instead of blocks | Interleaving: switching between kinds forces the brain to pick the rule, which is what an exam does |
| New words | Card, then the first retrieval comes **3–5 items later**, not straight after the card; second retrieval near the end of the session | Expanding retrieval inside the session; the first delayed recall is where the memory forms |
| Input | One text the kid can mostly read (coverage gate, 2.3), then the look-backs | Comprehensible input; words met in a story after being drilled get a second, meaningful trace |
| Output | One short production task: 2–3 sentences on a prompt (A2: "Schreib deiner Freundin, warum du morgen nicht kommst"), or say one sentence; checklist self-check plus a machine-checked piece (2.4) | Generation effect; the exam's writing and speaking parts are output |
| Wrap-up | "You learned 6 words and the dative after *mit*. 4 come back tomorrow. Last one: *der Bahnhof*" (a word they got right) | End on success; a short summary aids consolidation and makes the next session feel smaller |

Budget rules (replaces "size grows by date"):

- `session_minutes` per profile (default 25 school days, 40 weekends), estimated from the log's own per-item
  seconds (median of the last 200 attempts by task kind). The plan fills the budget: due reviews (most
  overdue, lowest box first) → new words (adaptive count, 3.2) → strengthen → text → output.
- Reviews that do not fit are **not dropped and not doubled tomorrow**; they stay due and keep first place.
  The app says so ("12 words wait for tomorrow") instead of silently piling up.
- A second run in the day is extra practice, as now, but never adds new words.
- Never end on a miss: the last item of the queue is a word from box ≥ 3.

### 2.2 The question types, adjusted

| Today | Change | Why |
|---|---|---|
| Speaking turn shows the German, kid reads it | **Say before you see**: cue is the English (or the gap sentence), kid says the German, speech check listens, then the German is shown and played | Turns reading aloud into retrieval; the speech check already exists |
| Card → typed straight after | Card → 3–5 other items → typed | Delayed first recall (2.1) |
| Grammar questions from any read sentence | Grammar questions sampled from the **frontier** grammar nodes (5.4), from sentences the kid has read or from word examples | Practises the rule that is being learned, not a random one |
| Word cards show one meaning | On a miss in box ≥ 2, the *example sentence* is shown as the cue next time (context cue) | A different retrieval route for a word that the bare cue fails on |

### 2.3 Input: the coverage gate

A text is **open** when at least 95% of its distinct words (after the same normalisation the scorer uses,
inflected forms mapped to headwords by the word bank and the verb list) are in box ≥ 2 or are function
words in `daily_function_words`. Under 90% it is locked and the app says why ("You know 78% of the words
in this paragraph. 31 to go, they are in your new words now"). Between 90 and 95 it is open with the
missing words pre-taught as that day's new words (as `reading_words` does today).

Consequences:
- The classics stop starting on day 1. Borchert opens around 2,500–3,000 words known; Kafka later.
- Until then the input step needs **graded readers**: short original texts (80–150 words) at A1/A2/B1 in the
  exam-text format (`content/readers/<level>_<nn>.json`, same shape as an exam reading text plus `words` and
  `explain_en`, no items). Roughly 40 per level. These are also the raw material for listening practice.
- The look-back ladder (1/3/7/16/35 days, five exercise kinds) applies to readers too; it works already.

### 2.4 Output and the cost of self-grading

Self-grades stay `estimated` (confidence 0.5). What changes is what follows one:

- **Prove it** (random 1 in 3 after "nailed it" or "mostly right"): one sentence of the same text, English →
  German typed, scored by the scorer. A miss lowers that event's confidence in the *next* event (the log
  stays append-only: a new `attempt` with `context: "prove"` referencing the self-graded event id) and the
  paragraph comes back next session.
- **Checklist self-grade for writing**: the task's `points` become tick boxes ("Did you say when? Did you
  say why?"), then 3 phrases from the model answer become gap cards for tomorrow. The kid grades coverage,
  the machine grades the phrases.
- The report shows self-grades and machine checks side by side, so "claimed" and "shown" are visible.

### 2.5 A week and a term

| Day | Session | Purpose |
|---|---|---|
| Mon–Fri | Daily loop, 20–25 min | Habit: same time, same length |
| Sat | "Mixed bag" 30–40 min: reviews + interleaved grammar set + one exam **part** (10 min) + a duel or async challenge | Retrieval under mild pressure; relatedness |
| Sun | Off, or free choice (extra practice, choose a book, listen to a reader) | Rest days are part of spacing; streak has one free "freeze" a week |
| Every 4–6 weeks | Progress check: 20 items across all open nodes (5.4), readiness shown against A2/B1 | Competence feedback; recalibration of the plan |
| When readiness ≥ 0.8 | Full mock exam (4.2), split over two days | Transfer to the real task |

Motivation, for 13–17-year-olds specifically: real anchors ("you know 61% of the words a Goethe A2 candidate
needs", not points), choice of topic packs (3.2), sessions that end when promised, a sibling to race, no
punishments (a caught paste is a redo, not a lecture), and the parent report as a conversation aid, not a
surveillance screen. Streaks count days, not items, and one missed day a week keeps the streak.

---

## 3. Placement, adaptation, leeches, and small fixes

### 3.1 Placement (first run, or opt-in from the menu for an existing profile)

About 15 minutes, all typed, all logged with `context: "placement"`:

1. **Vocabulary by frequency bucket**: 6 typed words (3 each way) from ranks 1–200, 201–500, 501–1,000,
   1,001–2,000, 2,001–3,500, 3,501–5,000. Stops after two buckets in a row under 50%.
2. **Grammar probes**: 3 items each for gender, case article, adjective ending, word order, Perfekt/Präteritum.
3. **One reader text** per level up to the highest vocabulary bucket passed, 3 questions each.

Result: an estimated band (A1 / A2 / B1 / B2) and a **seed**, never a guess written as knowledge:
- A bucket scored ≥ 80% → every unstarted word in it goes to **box 2, due spread over the next 14 days**
  ("confirm" reviews). One right answer sends it to box 3 (learned); a miss sends it to box 1, as any miss.
  So a wrong assumption costs one review, not a wrong "learned" count.
- Grammar probes and readers set the initial node state (5.3) but no boxes.
- Written as ordinary `attempt` events with `schedule: "result"` and a `seed` event listing the seeded ids,
  so `rebuild()` reproduces it. Existing profiles: only new events are added; nothing is rewritten.

### 3.2 Adaptation

| Signal (from the log, last 7 practice days) | Rule |
|---|---|
| Review accuracy < 70% | New words per day −2 (min 3); the wrap-up says "consolidating" |
| Review accuracy > 90% and time under budget | New words +2 (max 15) |
| Leeches > 10 active | New words −3 until under 10 |
| Practice days < 3 in a week | Budget unchanged; reviews only, no new words, until due count is under one session |
| Target level A2 | New words only from level ≤ A2 plus the next 200 by rank; `bank_shares` daily 0.9 / admin 0.05 / stem 0.05 |
| Target level B1 (work) | Level ≤ B1; daily 0.7 / admin 0.2 / stem 0.1 |
| Target level C1 (study) | All levels; daily 0.5 / admin 0.2 / stem 0.3 |

Teen tracks are just presets of the level cap, the shares and a **topic pack**: the kid picks 3–4 topics to
go first from the existing tags (`slang`, `texting`, `free-time`, `sport`, `music`, `food`, `travel`,
`social`, `school`, `technology`), and new words from those topics are picked before others of equal rank.
No content edit: the tags exist.

### 3.3 The Leitner boxes: one small change

Keep boxes 0–5 and their intervals. Add **box 6 = 75 days and box 7 = 150 days**. Reason: with a 35-day cap
every learned word returns 10 times a year for ever; at 3,000 learned words that is 80 reviews a day, which
is the 60-minute session. With 150 days it is ~20 a day and the budget holds. "Learned" stays box ≥ 3.
`rebuild()` keeps working because `apply_result` only reads `INTERVALS`; old events replay to the new ladder.

Recency decay for mastery (5.3) uses the same numbers: an item overdue by more than twice its interval is
treated as half as strong until it is reviewed.

### 3.4 Leeches

A word is a **leech** when its log shows ≥ 4 wrongs in total or 3 lapses from box ≥ 2 (derived, not stored).

| Leech count on the item | What changes |
|---|---|
| 1st time | Cue switches to the example-sentence gap; the app shows the word's `note` and asks the kid to type a 3–10-word memory hook of their own (stored in the profile, shown on every later miss) |
| 2nd | Paired with its most confused word (the wrong answer they gave, if it is a bank word) in a **discrimination card**: both shown, "which one is *to borrow*?" |
| 3rd | **Parked** for 30 days with a plain message ("Parked *leihen*; back on 25 Oct"). Out of the daily queue; listed in the report |
| Back from parking | Starts at box 1 with the sentence cue |

Leeches count toward adaptation (3.2) and are the first thing the report's "why stuck" shows (5.5).

### 3.5 Capital letters and other small fixes

- Typed German nouns with a lower-case first letter score **almost** ("right word, but nouns are capital in
  German: *der Hund*"), never wrong on the first offence, wrong on the repeat. Dictation already marks words;
  it gains a capitalisation flag per word. Listed under a new subcompetency `orthography.capitals`.
- One grammar kind added: **"groß oder klein?"** on a sentence with 3–4 words lower-cased.
- Umlaut/ß remain as they are (the scorer spec already handles `ae`/`ss` as almost).

---

## 4. Exam practice in the loop

The exam module and content format exist (`app/exams.py`, `CONTENT_FORMAT.md` "Exam practice"). This is
how it plugs into the loop.

### 4.1 Two sizes

| Size | When | What |
|---|---|---|
| **Exam part** (10–15 min) | From the Saturday session once level readiness ≥ 0.6; also offered on a weekday when the reviews are light | One part (Lesen Teil 2, Hören Teil 1…), timed loosely, explanations after each item |
| **Full mock** (A2 ~90 min, B1 ~2.5 h, split across two days) | Readiness ≥ 0.8, then every 4–6 weeks; two in the last month before a real exam | All modules, real timing, no explanations until the end, a per-module result against the 60% pass mark |

Readiness for a level = weighted mastery of the graph nodes tagged with that level (5.3): vocabulary sets
0.4, grammar 0.3, exam task types 0.2, texts 0.1. Shown as a bar with the anchor ("A2 readiness 0.72: words
0.81, grammar 0.64, exam tasks 0.55").

### 4.2 Every exam answer feeds back

Each exam item is logged as an `attempt` with competency `exam.reading` / `exam.listening` / `exam.writing`,
subcompetency = the part id (`a2.lesen-1`), item id `<exam>.<part>.<item>`, and `nodes`: the graph nodes the
item practises (its text's key words' vocabulary sets, the grammar points the author tagged). A miss does
three things next day:

1. The text's key words that are already started get `apply_practice(WRONG)` (box 1, tomorrow); unstarted
   ones jump the new-word queue.
2. Each tagged grammar node gets 3 extra questions spread over the next week.
3. The part's task type gets its own Leitner state (`exam:A2.hoeren.2`): a failed part is due again in 3
   days as a short part, a passed one in 16.
4. Writing: 3 phrases from the model answer become gap cards; the task's `points` return as the checklist
   for the next output step.

Mock results appear in the report as pass/fail per module with the two weakest nodes named.

---

## 5. The skill graph

### 5.1 Nodes

| Node type | Id pattern | Made from | Attributes |
|---|---|---|---|
| Vocabulary set | `vocab:A2/food`, `vocab:core-500` | `bank/level/topic` of existing words; rank buckets | level, item ids, size |
| Grammar point | `gram:A2.dative_articles` | `content/graph/grammar.json` (new, ~40 nodes A1–B2) | level, competency + subcompetency pattern it is scored from, prerequisites |
| Exam task type | `exam:A2.lesen.1` | exam files' parts | level, skill, pass mark |
| Text | `text:borchert-kurzgeschichten#12`, `text:reader-a2-07` | books and readers | level, distinct words → coverage |
| Competency (existing 12 + `exam.*` + `orthography.capitals`) | as in `attempts.COMPETENCIES` | | parent for all of the above |

### 5.2 Edges

- `requires` (prerequisite; a node is *open* when all prerequisites are *solid* or the placement said so)
- `practises` (item or task type → node; one item can practise several nodes)
- `unlocks` (text → needs coverage ≥ 95% over its vocabulary nodes)

A slice around A2 grammar:

```
 gram:A1.noun_gender ----requires----> gram:A1.nominative_accusative ---> gram:A2.dative_articles
        ^                                          |                              |
        | practises                                v                              v
 grammar.noun_gender items              gram:A2.adjective_endings <---- requires -+
 (der/die/das cards)                               ^
                                                   | practises
 gram:A1.present -----> gram:A2.perfekt -----> gram:B1.praeteritum      grammar items from
        |                    ^                                          read sentences,
        v                    | practises                                exam items (nodes tag)
 gram:A1.main_clause_order --+--> gram:A2.subordinate_order --> gram:B1.relative_clauses
                                            |
                          vocab:A2/travel   | unlocks (coverage >= 95%)
                          vocab:A2/family --+--> text:reader-a2-07 --> exam:A2.lesen.1
```

Grammar node definition (data, not code):

```json
{"id": "gram:A2.dative_articles", "level": "A2", "title_en": "Articles in the dative (dem, der, den, einem)",
 "requires": ["gram:A1.nominative_accusative"],
 "scored_from": {"competency": "grammar.case_articles", "subcompetency": "article:dat*"},
 "examples": ["mit dem Bus", "bei einer Freundin"]}
```

Existing grammar events carry only `article` / `ending` / `order` as subcompetency; they map to the parent
level node (`gram:A1-A2.case_articles`). New events add the case (`article:dat`, `ending:acc-indef`,
`order:subordinate`), which the grammar module can tell from the case tip it already computes. No
migration: old events count for the parent, new ones for the child.

### 5.3 Mastery from the answer log

Per **item** (a word, verb form, gender, exam item), from the rebuilt box and the last review:

| box | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| strength | 0 | 0.15 | 0.35 | 0.6 | 0.75 | 0.9 | 1.0 | 1.0 |

halved when overdue by more than twice the box interval; leeches capped at 0.35.

Per **node**:
- Vocabulary set and text: `mastery = mean strength over items` and `coverage = started items / items`.
  Both shown; a set can be 100% covered and 40% strong.
- Grammar point and exam task type (items are generated or few): exponentially weighted accuracy over the
  matching `attempt` events (half-life 20 attempts), `dichotomous` and `polytomous` only; `estimated`
  (self-graded) events are shown as a separate "claimed" number at their `confidence`; `no_response` counts
  as wrong for mastery but not for the accuracy shown to the kid.
- Confidence = number of attempts in the last 60 days (< 10 → "not enough data", never "weak").

Node **state**: `locked` (a prerequisite not solid) → `open` → `practising` (≥ 10 attempts) → `solid`
(mastery ≥ 0.8, ≥ 20 attempts, no leech cluster in it) → `rusty` (was solid, mastery fell under 0.65 by
decay). All of it is computed from the log and the content at start-up (8,400 items: well under a second)
and cached in the profile under a key `rebuild()` can drop.

### 5.4 What next

The graph never overrides spacing; it fills the room spacing leaves.

1. Due reviews first (Leitner), always.
2. **Frontier** = open nodes whose prerequisites are solid, tagged ≤ target level + 1. New words come from
   frontier vocabulary sets in rank order (topic pack first). Grammar questions: 70% from frontier grammar
   nodes (the one with the lowest mastery first), 30% from solid nodes (maintenance, interleaving).
3. Input: the highest-level text with coverage ≥ 95% that is not yet read; ties go to the current book.
4. Output prompt: from the frontier grammar node's `examples` and the day's topic.
5. Exam part offered when readiness ≥ 0.6, the weakest task type first.
6. If nothing is open (all prerequisites weak): the weakest prerequisite chain becomes the plan, and the
   wrap-up says so ("Before adjective endings: the dative articles, 61%").

### 5.5 The parent report: "why is my kid stuck"

For every node that is `practising` with flat mastery over 3 weeks, or `rusty`, the report prints one block:

```
Stuck: Adjective endings (A2)  52%, 41 tries in 3 weeks, flat
  because: Articles in the dative 61% (not solid yet)  -> practise that first (the app already does)
  and:     7 leeches in "daily/food", 2 parked (leihen, die Gabel)
  time:    3 practice days a week, 14 min each: 19 reviews wait every day
  try:     a 10-minute Saturday mixed bag; ask them for the memory hook they wrote for "leihen"
```

The four lines come straight from the graph (prerequisite chain), the leech list, the log's timestamps
(practice days, minutes, overflow), and a fixed table of suggestions per cause. Nothing is guessed.

---

## 6. Data and export (Route C)

| Data | Where | Export |
|---|---|---|
| Graph nodes and edges | `content/graph/*.json` (grammar written by hand; vocabulary, text and exam nodes derived at load) | `competencies.json` grows a `nodes` list with `requires`/`practises` edges: the platform schedules on its own, the graph is content |
| Per-event node tags | new optional `nodes: [...]` and finer `subcompetency` on `attempt` events | already in `attempts/<name>.jsonl` |
| Placement seed | `seed` event + `attempt` events with `context: "placement"` | as attempts |
| Prove-it link | `attempt` with `context: "prove"`, `about: <event id>` | as attempts; the platform decides how to use it |
| Leech, parked, node mastery, readiness | **derived**, cached in the profile, dropped by `rebuild()` | not exported; the platform computes its own |
| Memory hooks, topic pack, target level, budget | profile settings | exported as learner preferences, if the platform wants them |

Rules kept: ids never change; item versions as today; `no_response` stays its own kind; self-graded stays
`estimated`; nothing rewrites history.

---

## 7. Prioritised build plan

Each step ships on its own and is useful without the ones after it. "Learning impact" is the expected effect
on retention or on the chance the kid keeps practising.

| # | Step | What changes | Learning impact | Effort | How to test |
|---|---|---|---|---|---|
| 1 | **Session budget and priority order** | `session_minutes` per profile replaces size-by-date; per-item seconds from the log; due reviews most-overdue-first, overflow stays due and is announced; last item from box ≥ 3; wrap-up screen | High: fixes the 60-minute drop-out risk; nothing piles up silently | S | Unit test: a profile with 800 due words plans ≤ budget and the rest stays due; wrap-up text in a snapshot test; a kid's real session under 30 min |
| 2 | **Teen tracks** | Target level per profile (A2 / B1 / C1) caps new-word level and sets `bank_shares`; topic pack chosen from existing tags picked first at equal rank | High for motivation: fewer STEM/official words at A2, words they will meet | S | Test `pick_new_words` with the A2 preset: ≥ 90% daily, none above A2+200 rank; topic-pack words first |
| 3 | **Leeches, capitals, say-before-see** | Leech ladder (sentence cue, memory hook, discrimination card, parking); nouns without a capital score *almost*; speaking turns cue with English, reveal after | Medium–high: stops the same miss repeating; adds orthography the exam tests; makes speaking retrieval | M | Tests on `rebuild()`-derived leech status; scorer vectors for capitals added to `tests/vectors`; manual mic run |
| 4 | **Exam practice v1** (in progress) | Ship A2/B1 practice exams and the module; log every item with `exam.*` competency, part id, `nodes`; exam-part mode (one part, 10 min) from the menu; best score per part in the profile | Medium now, high later: transfer to the real task; the log tags make steps 7–8 possible | M | `validate_content.py` on the exam files; test that an exam run writes one event per item with the right ids; a kid does one part |
| 5 | **Placement** | 15-minute typed placement; band estimate; seeds boxes at box 2 spread over 14 days; opt-in for existing profiles | High for a new or returning kid: right difficulty from day 1, no months of A1 words for a kid at A2 | M | Test: a scripted "A2 kid" answering the placement lands in band A2 and seeds ~1,200 words at box 2; `rebuild()` reproduces the seed |
| 6 | **Ladder to 7 boxes and adaptive new words** | `INTERVALS` gains 6: 75, 7: 150; new-word count from last 7 days' accuracy and leech count | Medium: keeps daily reviews ~20 at 3,000 words; keeps success near 80–85% | S | Simulation over 365 days with a 85%-accuracy learner: mean daily reviews and words learned before/after; `rebuild()` on an old log |
| 7 | **Skill graph v1 and "why stuck"** | `content/graph/grammar.json` (~40 nodes with prerequisites); derived vocabulary/text/exam nodes; mastery, states and readiness bar; grammar events carry the case in `subcompetency`; parent report block | Medium for the kid (competence feedback), high for the parent (actionable causes) | M | Tests on mastery from a synthetic log (decay, leech cap, confidence); a fixture "stuck" profile renders the expected report block |
| 8 | **Graph-driven what-next and exam feedback** | Frontier picks new words and grammar questions; readiness gates exam parts and the full mock; exam misses push words, grammar and part types back into the daily plan; mock schedule every 4–6 weeks | High: practice aims at the next thing that is learnable and at exam weaknesses | M | Test: with dative at 0.5, ≥ 70% of grammar questions are dative; a failed Hören part is due in 3 days; the day after a mock, the plan contains its missed words |
| 9 | **Graded readers and the coverage gate** | 40 short original texts per level at A1/A2/B1 in the exam-text shape; coverage computed per text; books lock/unlock by coverage; look-back ladder applies | High: comprehensible input at 95–98% is the missing half of the method; the books become a reward, not a wall | L (content) | `validate_content.py` for readers; test coverage maths on a fixture profile (Borchert locked at 1,200 words, open at 3,000); a kid reads one at 96% and grades it |
| 10 | **Prove-it checks and graph export** | Prove-it sentence after 1 in 3 self-grades; writing checklist + phrase gap cards; `competencies.json` exports nodes and edges; events carry `nodes` | Medium: makes self-grades honest; keeps Route C whole | S–M | Test that a prove-it event references the self-graded event id; exporter test that nodes/edges round-trip; a kid's writing task produces 3 gap cards next day |

Order rationale: 1–3 change how every session feels and are cheap; 4 is already under way and its event
tags are needed later; 5–6 make the plan right for each kid; 7–8 add the map and use it; 9 is the largest
piece of content work and depends on the gate maths from 7; 10 closes the honesty and export loops. Steps
1, 2, 6 and 10 are safe to ship in one release each; 4, 7 and 9 want a kid to try them before the next one.
