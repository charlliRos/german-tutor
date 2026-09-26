# Recommendations not built yet

Everything recommended for gtutor that isn't built yet, in one place (as of 2026-09-26). For each: why, what to
build, and **where it belongs**, in the app or on the family learning platform's server (the Rust Open Learning
Runtime, see [OLR_INTEGRATION.md](OLR_INTEGRATION.md)). Once gtutor is integrated and online, every kid's answers
are in one place, so anything that compares kids or items across computers belongs on the server.

Already built, for reference: the learning design's 10 steps ([LEARNING_DESIGN.md](LEARNING_DESIGN.md)), exam
practice A2/B1 with pictures, voices, worked examples, speaking and writing checks, the Smart App Control work,
graded readers, smarter English matching and the claims review (`tools/review_claims.py`).

Contents: 1 Study intent (goofing vs. serious effort) · 2 Item analysis (questions that are the problem) · 3 Open
items from the 2026-09-25 review · 4 Smaller open items · 5 Not verified on a real device yet.

---

## 1. Study intent: goofing vs. serious effort

**Question from the parent:** should the app punish kids who goof around and reward serious intent, or treat
everybody the same?

**Verdict (Astra's opinion, 2026-09-26, and I agree):** the same respect and the same rules for everyone, with
different *help* for each kid. No punishment for what the app guesses a kid intended, and no "serious kid" score.
Research on teenage motivation (self-determination theory) says teens learn best with some choice, a sense of
getting better, and belonging. Punishment and control work against all three. Paying for effort (points per
minute, per correct answer) invites waiting, deliberate mistakes and inflated claims (the overjustification
effect). Rewards should show real progress ("you remembered 8 of 10 from last week"), not buy obedience.

**Read patterns, not minds.** The same data can mean different things:

| Pattern in the answer log | What it may mean | What the app should do |
|---|---|---|
| Very fast nonsense or copied text, again after an explanation | Skipping the task | No credit; one retry, then help or a pause |
| Many `?` answers and plausible mistakes on new material | Too hard | Show an example, fewer new words, a shorter text; `?` stays safe |
| Mistakes pile up late in a session, pauses and early exits | Tired or interrupted | Offer to stop; keep the work done |
| Confident self-grades, then failed memory checks | Misunderstanding the rubric, weak recall, or a checker error | Show the difference; teach self-checking |
| Many "my answer was right too" claims | Often the word bank is too narrow | Review the claims before blaming the kid (see section 2) |
| Fast and accurate | Fluent, or too easy | Offer more challenge |

Compare each kid with **their own** history, for the same kind of task and level, as rates (with how many
attempts). Answer gaps in the log aren't clean thinking times.

**One thing today is effectively a punishment:** when a translation is caught as random or copied, the whole
paragraph restarts and comes back in 2 extra sessions, and in look-backs catches can keep adding sessions.

### The changes, most impact first

| # | Change | Data | Kid sees | Parent sees | Where |
|---|---|---|---|---|---|
| 1 | **One retry instead of punishment**: after a caught answer, one retry, then help or come back later. No stacking of extra sessions. **My one exception:** keep that single redo (the redo is learning), only drop the stacking. | catch reason, item id | the next useful step | rejected input and what happened after | app (`app/reading.py`) |
| 2 | **Help / pause menu** after several misses or rejected inputs in a row: "too hard / tired / input problem / try again". The app eases the load (easier text, fewer new words, stop). | recent results | a way out that isn't failing | the kid's reason, labelled as self-report | app |
| 3 | **A kinder parent report**: "Inputs that needed a retry: 3, two retried successfully" instead of "Cheating caught", with trend and examples, and the prompt "What was happening here?" | catches + retries | (same as the parent) | a conversation starter, not a verdict | app (`app/report.py`); later the platform |
| 4 | **Log how sessions end** (finished, time budget reached, paused, quit) **and the time from question to answer**. | new session-end events; answer duration | saved progress | interruptions, without invented motives | app (log); analysis on the server |
| 5 | **Rename "Prove it" to "Memory check"**: it sounds less like an accusation. Pair self-grades with check results in the report (with how many). | self-grade + check events | specific feedback | claimed vs. shown, side by side | app |
| 6 | **A finish screen about learning**: first-try results and later recalls ("Remembered 8/10 from last week"). Cap collectibles per day; easy repeats earn nothing extra. | answer log | real progress | the same evidence | app |
| 7 | **Rivalry you can choose**: duels stay, with an accuracy-only mode and weekly resets; personal goals follow each kid's level and time; celebrations are shared, mistakes and flags stay private. Fairness = the same rules and chances, not the same workload or raw scores. | duel scores, goals | a fair race | (nothing extra) | app; leaderboards later on the platform |

Keep: paste rejection, the held-Enter filter, the protected `?`, the claims review, occasional memory checks.
Replace the accusing buzz and message with "That input wasn't accepted: type an answer, or choose help."
Avoid screen-time rewards per correct answer. If the family has a deal, agree on a routine with stop rules;
automatic flags shouldn't take it away. Keep forgiving streaks and a regular time of day (a habit cue).

---

## 2. Item analysis: questions that are the problem, not the kids

**Idea from the parent:** if certain questions are answered wrong again and again, the question may be the problem.

A **hard word** (one kid keeps missing it) is normal: spaced repetition and the leech ladder handle it. A **bad
question** shows up **across kids**:

| Pattern across attempts | Likely question problem | Fix |
|---|---|---|
| The same "wrong" answer again and again, from different kids or days (e.g. "to awaken" for *aufwachen*) | A correct answer the bank doesn't know | Add it as an accepted answer (like the claims review, but found even when nobody pressed `o`) |
| Mostly "almost", with the same small difference | Accepted spelling or keyword list too narrow | Add the spelling, widen the list |
| Exam: most wrong answers pick the same wrong option | Ambiguous question, or a wrong answer key | Re-check the question against its text (a person or Astra) |
| Listening, dictation or speaking often wrong where the kid knows the words elsewhere | The voice mispronounces it, or the speech check can't hear it | Listen to it; fix the text, or switch off that check for that item |
| Much harder than other items of the same level (an "A1" word missed 80% of the time) | Wrong level label, or a confusing English prompt | Relabel, or reword the prompt |

**Rules for flagging** (so thin data doesn't accuse a question):
- at least 5 attempts on the item's **current version**, from at least 2 kids or 3 different days;
- only **first attempts** count (context `warmup.new` / `warmup.review` / `exam.*`, not `warmup.repeat` or
  placement), so repeats of an already-missed word don't inflate the rate;
- flag when, for example, the same normalised wrong answer appears 3+ times, or the wrong rate is 60% while items
  of the same level and task are around 20%;
- "worth a look", never "broken". A person or Astra decides.

**Fixes go through item versions:** adding an accepted answer, rewording or relabelling bumps the item's version
(`content/item_versions.json`), so its statistics start fresh, which is the platform's own rule.

### Where it belongs: the platform server

Item analysis compares many kids and needs all their answers together. Today each computer only has its own kids'
answer logs. **Once gtutor is on the platform and online, this belongs on the server**, where all the data is in
one place and it can run for every item continuously.

gtutor already logs and exports everything the server needs (`tools/export_olr.py`, one event per answer):

| Field | Used for |
|---|---|
| `item`, `item_version` | grouping by question; statistics reset per version |
| `learner` | "across kids", not one kid's leech |
| `context`, `task` | first attempts only; direction (en2de / de2en / gap / dictation / exam part) |
| `response` | the most common wrong answers |
| `score` (Dichotomous / Polytomous / Estimated), `grader` | right, almost, wrong; machine vs. self-graded kept apart |
| `machine_verdict`, `claimed_correct` | claims next to the checker's verdict |
| `competency`, `subcompetency`, level (from the item) | comparing with similar items |
| `at` | days apart; trends |

Still to add in gtutor for better analysis: the time from question to answer, and session-end events (change 4 in
section 1).

What the server should hand back: a list of flagged items with the evidence, and, once a fix is decided, a new
content package version with the item changed. gtutor's content files stay the source of the German content
until then.

**Interim, before integration:** a small local tool (`tools/review_items.py`) could do the same on one computer
(and on copied `data/profiles` folders from other computers). Only worth building if integration is far off.

---

## 3. Open items from the 2026-09-25 review

The review covered UI, performance, learning, security and compatibility. Most learning and security findings are
fixed; these are still open (all app-side):

**UI**
- Dictation marks right / small slip / wrong by colour only: add a text mark per word, for colour-blind kids and
  no-colour terminals (`app/reading.py` `mark_words`).
- Key options run into one long line that wraps at 80 columns: one option per line when there are many.
- In "Choose a book", `s` restarts a book without asking; everywhere else `s` is harmless. Use another key and
  ask "Sure?".
- A Wi-Fi sharing problem is shown among the sound problems on every menu screen: keep it apart.
- Some errors still show raw technical text; show a plain sentence and log the details.
- "N content problems, run tools/validate_content.py" is shown to kids at start: show it only in the report.
- Ctrl+C outside a prompt can close the whole app instead of just the activity.
- The welcome doesn't mention `?` = don't know.
- On Linux, typing during audio is echoed and then thrown away.
- Small: an "almost" verb answer shows a red panel; titles measure width with `len()`; an empty duel answer gives no
  hint; no plain/screen-reader mode (spinners, cleared scroll-back).

**Performance** (nothing urgent)
- The voice and speech checker load after the name is typed (~3 s until the first word): load them in the
  background while the name is chosen.
- The content load takes ~0.8 s each start: cache it.
- The profile is rewritten with indentation after every answer: write it compactly (~6× faster, 32% smaller).
- Looking up words with the same English meaning scans all 8,400 words (52 ms after a wrong answer): index it once.
- Wi-Fi announcements can reach 14 KB: send challenges only when they change.
- The speech cache is never emptied in a session: cap it.
- Reading the journal reads the whole file: read only its end.

**Compatibility**
- `setup.bat` still stops completely if one download fails; `setup.sh` no longer does.
- `setup.bat` doesn't check for 64-bit Python 3.9+.
- ChromeOS / hotspot addresses (100.64.0.0/10) are refused by the Wi-Fi code.
- When input isn't a real terminal (PowerShell ISE, Git Bash), paste blocking is silently off: warn.

**Security**
- Kids on the Wi-Fi aren't authenticated: anyone on the same network could pretend to be one of them (documented in
  the README). Fix: pair once with a shared code and sign messages.
- "Only the local network" accepts any private address, not just this network: accept only the own subnet.
- Downloads (voice, speech model) aren't checked against a SHA-256.
- Libraries aren't pinned to exact versions with hashes; updates trust GitHub completely (no signed commits).
- The translation journal is kept forever: document it, or cap it.
- The voice name from config.json isn't checked before it becomes a file path.

**Learning**
- Extra practice on a word that isn't due resets it to box 1 on a miss: lower it one box instead.
- Short English prompts for small words are ambiguous ("just, once" for *mal*): use the example sentence with a gap.

---

## 4. Smaller open items

- Two parts of the learning design aren't built: the **discrimination card** for words that get confused with
  each other (leech ladder step 2), and turning phrases from a writing task's model answer into **gap cards** for
  the next days.
- English matching doesn't know irregular plurals (child / children).
- A **code-signing certificate** (about €25–70 a year) would let the offline speech checker (Vosk) run under
  Smart App Control too; today the Windows speech recognizer is the fallback. Declined for now (free fixes chosen).
- The app needs Python and numpy to start at all; if a policy ever blocked numpy, it couldn't run.
- DARES design (the platform's CPNS product) is with the platform session; nothing to do in gtutor.

---

## 5. Not verified on a real device yet

Tested by the test suite and scripted runs, but not yet seen or heard by a kid:
- the countdown before recording, the automatic next question and its 4-second wait;
- the voices (pitch-shifted speakers) and the speaking section with a real microphone;
- pictures in real pixels (sixel) in Windows Terminal (menu 7 has a test picture);
- the fallbacks on a Smart App Control computer: prepared pronunciations, ready-made pictures, the Windows speech
  check (needs the German speech pack);
- macOS setup.
