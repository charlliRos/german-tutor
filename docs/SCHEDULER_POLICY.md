# gtutor's scheduling policy (for the OLR core scheduler)

On the Open Learning Runtime, the core owns scheduling (two schedulers can't own one learner). The platform's
developer kit (ADR-037) plans a core scheduler that **accepts an app's policy**. This is gtutor's policy, written as
settings plus the rules that use them, so the core scheduler can be designed to express it. Values are the ones
the Python app uses today (app/srs.py, app/warmup.py, app/placement.py, app/reading.py, app/exam_practice.py,
app/goals.py). The reasoning behind them is in [LEARNING_DESIGN.md](LEARNING_DESIGN.md).

Everything here is **per learner** and **derived from the append-only attempt log** (the boxes can be rebuilt from
the log, including seeds and nudges; see app/attempts.py `rebuild`).

## 1. The ladder (words, verb forms, der/die/das)

| Setting | Value |
|---|---|
| `boxes` | 0–7 (0 = not started) |
| `intervals_days` | box 1: 1 · 2: 3 · 3: 7 · 4: 16 · 5: 35 · 6: 75 · 7: 150 |
| `learned_from_box` | 3 |

Rules per graded answer (`result`):
- **right** → box + 1 (max 7), due in that box's interval;
- **almost** → box stays (at least 1), due tomorrow;
- **wrong** → box 1, due tomorrow; wrong count + 1.

Extra practice on an item that isn't due (`practice`): a miss is handled like **wrong** (proposed change: one box
down instead); a right answer doesn't move the box and doesn't skip ahead.
A spoken answer the speech check heard, on an item that was due (`practised`): box stays, due tomorrow at the earliest.

## 2. Items that keep slipping (leeches)

| Setting | Value |
|---|---|
| `leech_wrongs` | 4 wrongs in all while under the learned box → a leech |
| `park_after` | 8 wrongs → parked (not asked) for `park_days` = 30; after that, every 4 more wrongs park it again |

A leech changes the **cue**, not the schedule: it's asked with its example sentence (a gap) instead of the bare
word, and the learner is asked for a memory hook once. The scheduler needs to expose "is leech" and "is parked"
to the app, and to let a leech ask for another question type.

## 3. A day: the time budget

| Setting | Value |
|---|---|
| `session_minutes` | weekday 25, weekend 40 (per-learner override allowed) |
| `warmup_share` | 0.6 of the minutes go to reviews and new items; the rest to reading and one exam part |
| `seconds_per_item` | the median gap between answers in the learner's last 200 warm-up answers (gaps 2–120 s); 20 s until 20 gaps are known |
| `warmup_min` / `warmup_max` | 10 / 200 items |

Items today = the time budget ÷ seconds per item, within min and max. Order:
1. **Due items first**, most overdue first, lower box first. Due items that don't fit **wait** (they keep
   first place tomorrow); they're never doubled up.
2. **New items** only in the room the due items leave, up to today's new-item number (§4).
3. Then **practice** on started items (weakest and least recent first).
4. Early on, when few items are started, the room left is filled with new items.
5. The day **ends on an item the learner knows** (box ≥ 3), if one is in the queue.

Missed items come back at the end of the session "until right" (practice only: no effect on the ladder).
A claimed answer ("my answer was right too") counts as right and comes back once more that session.

## 4. New items per day (adaptive)

| Setting | Value |
|---|---|
| `new_share` | 0.25 of today's items |
| `new_min` / `new_max` | 3 / 15 |

Adjusted from the last 7 practice days:
- reviews under 70% right (almost = half) → 2 fewer;
- over 90% → 2 more (still at most `new_max`);
- more than 10 active leeches → 3 fewer;
- fewer than 3 practice days in the last 7 **and** a full session of items due → **no new items** until caught up.

The app shows the reason when the number changes.

## 5. Which new items: goal, level, topics

| Goal | Levels of new words | Extra | Mix of word lists (everyday / official / STEM) |
|---|---|---|---|
| A2 | A1, A2 | + the next 200 most common words above | 0.9 / 0.05 / 0.05 |
| B1 | A1–B1 | + the next 200 | 0.7 / 0.2 / 0.1 |
| C1 | all | — | 0.5 / 0.2 / 0.3 |

New words go by frequency rank; the lists are mixed by their share (the list furthest behind its share goes
next). Up to 4 **favourite topics** go first among words within 500 frequency ranks of each other (a favourite
never jumps far more common words). Words from the books join when their paragraph is read (a queue in front of
the new words, up to 16 a day, known ones again as practice).

## 6. Placement (a seed, not answers)

Six frequency bands (ranks 1–200, 201–500, 501–1,000, 1,001–2,000, 2,001–3,500, 3,501–5,000), 6 typed words each;
it stops after two bands in a row under 50%. A band with 80%+ right is known: its unstarted words go to **box 2,
due spread over the next 14 days** (each is checked once: right → learned, wrong → box 1). Recorded as one
**seed event** in the log. Band → level: A1, A1, A2, A2, B1, B2.

## 7. Paragraphs (reading)

A new paragraph comes back in each of the **next 2 sessions**, and on **days 1, 3, 7, 16, 35** after it was
learned, each time with a different exercise type than last time. A look-back counts only if it went well; one
good look-back clears the current session and every review day that has come. A missed "memory check" adds one
session. (Today a caught random/copied answer adds 2 sessions; the recommendation is to drop that stacking:
RECOMMENDATIONS.md §1.)

## 8. Exam parts

An exam part is due again **3 days** after a failed try (under 60%), **16 days** after a passed one. Each wrong
answer brings up to 15 words from its texts back: started words get a `practice`-wrong (tomorrow, box 1) as a
**nudge event**; unstarted ones join the front of the new-word queue.

## 9. What the core scheduler needs to offer for this

- Per-app ladders with their own intervals, the result rules (right / almost / wrong) and practice vs. result.
- A per-learner **time budget** and a pace estimate from the log, with due-first ordering and "wait, never double".
- **Adaptive new-item counts** from recent accuracy, leeches and missed days.
- Item **eligibility filters** (level caps, list shares, topic preference, a queue of item ids pushed by the app).
- **Seed** and **nudge** events (boxes set without an answer), rebuildable from the log.
- Exposing item state (box, due, leech, parked) to the app, so it can choose the question type.
- Session-scoped repeats (until right) that don't touch the ladder.
- Separate schedules per item kind (words, verb forms, genders, paragraphs, exam parts).

## 10. Rulings for the OLR rewrite (owner, 2026-09-26, binding for the ADR-037 SDK)

Almost everything above becomes **integer / permille settings in the app manifest**, run by the core scheduler:
the ladder and intervals, the right / almost / wrong rules, non-due practice, the time budget (the core works out
the pace from answer timestamps; the app never sees it), adaptive new items and caught-up mode, eligibility via
content tags, per-kind schedules (a new "steps" family for paragraphs, "pass_fail" for exam parts), session
repeats, and speaking turns (the attempt gets a host-set `input_path`: typed or speech).

Four things change shape:

| | Today (Python app) | On OLR |
|---|---|---|
| A. Book words, exam misses, placement | The app pushes **seed** and **nudge** events | The **core** derives them from **content links** and **tagged placement items**, by rules gtutor declares. The app can't push seeds or nudges. |
| B. Leeches | The app knows "is leech / is parked" and switches to the sentence cue | The leech stays due and the **core swaps in a content variant tagged `cue:leech`**; parking and return are the core's. The app is never told. **Leech-cue variants (e.g. the example-sentence gap) must be authored as content.** |
| C. Goal, topics, minutes | Asked and stored by the app | A **platform settings screen** stores them; the app can't read them back. |
| D. "My answer was right too" | The app's `o` key, the claims review | A **platform appeal button**: it counts as right pending parent review. |

What this means for the rewrite's content work: every word needs its leech-cue variant as content, book key words
and exam texts need content links to the words they contain, placement needs tagged placement items, and the
goal/level/topic rules become content tags plus declared rules.
