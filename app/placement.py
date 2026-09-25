"""Placement: about ten minutes of typed words by frequency band, then a few der/die/das and grammar
questions (docs/LEARNING_DESIGN.md 3.1). For a kid who already knows some German.

A band answered at least 80% right counts as known: its unstarted words go to box 2, due spread over the next
two weeks, so each is checked once ("confirm" reviews). A wrong guess costs one review, never a false
"learned". The seed is one event in the answer log, so rebuild() reproduces it.
"""
from __future__ import annotations

from datetime import timedelta

from rich.panel import Panel
from rich.text import Text

from . import attempts, genders, grammar, sfx, srs, ui
from .answers import ALMOST, CORRECT, WRONG, check_english, check_german
from .content import READING
from .ui import console, icon

BUCKETS = [(1, 200), (201, 500), (501, 1000), (1001, 2000), (2001, 3500), (3501, 5000)]
BANDS = ["A1", "A1", "A2", "A2", "B1", "B2"]   # the level if this band (and the ones before) is known
PER_BUCKET = 6
KNOWN = 0.8        # this share right: the band counts as known
STOP_BELOW = 0.5   # two bands in a row under this: stop, it's too hard from here
SEED_BOX = 2
SPREAD_DAYS = 14
PROBES = 3         # der/die/das and grammar questions each


def bucket_words(words: dict, lo: int, hi: int, rng, count: int = PER_BUCKET) -> list:
    pool = [w for w in words.values() if w.bank == "daily" and lo <= w.rank <= hi and w.pos != "phrase"
            and w.bank != READING]
    rng.shuffle(pool)
    return pool[:count]


def ask(ctx, word, direction: str, heading: str) -> str:
    """One quick typed question: no card, no sound, just right or wrong (it's a test, not a lesson)."""
    ui.clear()
    ui.title(heading, "placement: not a lesson, just finding your level")
    if direction == "en2de":
        ui.todo("type", what="Type the German word" + (" with der / die / das." if word.pos == "noun" else "."))
        console.print(Panel(Text(", ".join(word.en[:2]), style="bold green"), title="English → German",
                            border_style="green", padding=(0, 2)))
        answer = ui.ask_answer("German:")
        check = check_german(answer, word, ctx.content.real_de) if answer else None
    else:
        ui.todo("type", what="Type what it means in English.")
        console.print(ui.german(word.de, "German → English", word=True))
        answer = ui.ask_answer("English:")
        check = check_english(answer, word, ctx.content.real_en) if answer else None
    outcome = check.outcome if check else WRONG
    console.print({CORRECT: f"[good]{icon('ok')}[/]", ALMOST: f"[almost]{icon('almost')} {ui.escape(check.message if check else '')}[/]",
                   WRONG: f"[bad]{icon('bad')}[/] [hint]{ui.escape(word.de)}[/]"}[outcome])
    attempts.note(answer, outcome, check.message if check else "", direction)
    attempts.record(ctx.profile, ctx.today, item=word.id, item_version=attempts.word_version(word),
                    competency=attempts.WORD_TASKS[direction], subcompetency=attempts.word_subcompetency(word),
                    context="placement", score=attempts.graded(outcome) if answer else attempts.no_response("don't know"),
                    grader=attempts.GRADER)
    ui.pause(0.8, skippable=True)
    return outcome


def seed(ctx, lo: int, hi: int, start: int = 0) -> dict[str, dict]:
    """Box 2 for every unstarted everyday word in the band, due spread over SPREAD_DAYS (starting tomorrow)."""
    states = ctx.profile.data["vocab"]
    seeded = {}
    fresh = sorted((w for w in ctx.content.words.values() if w.bank == "daily" and lo <= w.rank <= hi
                    and states.get(w.id, {}).get("box", 0) == 0), key=lambda w: w.rank)
    for n, w in enumerate(fresh, start):
        due = ctx.today + timedelta(days=1 + n % SPREAD_DAYS)
        seeded[w.id] = {**srs.new_state(), "box": SEED_BOX, "due": due.isoformat(), "seeded": ctx.today.isoformat()}
    return seeded


def run(ctx) -> str:
    """The placement. Returns the estimated level (A1, A2, B1, B2)."""
    attempts.start(ctx.profile)
    ui.clear()
    ui.title("Find your level")
    console.print(Panel(Text.from_markup(
        "About ten minutes. First words, from the most common ones up; it stops by itself when they get too "
        "hard. Then a few der/die/das and grammar questions.\n\n"
        f"Don't know one? Type [bold]{ui.DONT_KNOW}[/]: that's the point, nobody knows them all. "
        "Words you clearly know are checked once more over the next two weeks, then left alone."),
        border_style="magenta", padding=(1, 2)))
    ui.keys({"": "start"})
    scores, low = [], 0
    for b, (lo, hi) in enumerate(BUCKETS):
        chosen = bucket_words(ctx.content.words, lo, hi, ctx.rng)
        if not chosen:
            break
        right = 0.0
        for i, word in enumerate(chosen):
            outcome = ask(ctx, word, "en2de" if i % 2 else "de2en",
                          f"Words {b + 1} of {len(BUCKETS)} · {i + 1} of {len(chosen)}")
            right += {CORRECT: 1.0, ALMOST: 0.5}.get(outcome, 0.0)
        scores.append(right / len(chosen))
        low = low + 1 if scores[-1] < STOP_BELOW else 0
        if low == 2:
            break
    known = [b for b, score in enumerate(scores) if score >= KNOWN]
    seeded: dict[str, dict] = {}
    for b in known:
        seeded |= seed(ctx, *BUCKETS[b], start=len(seeded))
    if seeded:
        ctx.profile.data["vocab"].update({wid: dict(s) for wid, s in seeded.items()})
        attempts.record_seed(ctx.profile, ctx.today, "vocab", seeded)
    probes = _probes(ctx)
    band = BANDS[max(known)] if known else "A1"
    ctx.profile.data["placement"] = {"date": ctx.today.isoformat(), "band": band,
                                     "bands": [round(s, 2) for s in scores], "seeded": len(seeded), **probes}
    ctx.profile.save()
    ui.clear()
    ui.title("Your level")
    sfx.play(ctx.audio, "right")
    console.print(f"[good]{icon('party')} About [bold]{band}[/].[/]")
    if seeded:
        console.print(f"{len(seeded):,} words you most likely know were added. Each comes back once in the next "
                      f"{SPREAD_DAYS} days to check; the ones you really know then leave you alone.")
    else:
        console.print("We'll start with the most common words.")
    for label, (right, total) in probes.items():
        if total:
            console.print(f"[hint]{label.replace('_', ' ')}: {right} of {total} right[/]")
    ui.keys({"": "continue"})
    return band


def _probes(ctx) -> dict[str, list[int]]:
    """A few der/die/das and grammar questions (logged; they tell the skill graph where grammar stands)."""
    out = {"der_die_das": [0, 0], "grammar": [0, 0]}
    nouns = [w for w in ctx.content.words.values() if w.bank == "daily" and genders.eligible(w) and w.rank <= 1000]
    ctx.rng.shuffle(nouns)
    for i, word in enumerate(nouns[:PROBES], 1):
        outcome = genders.log(ctx, word, "placement", genders.card(ctx, word, f"der, die, das {i} of {PROBES}"))
        out["der_die_das"][0] += outcome == CORRECT
        out["der_die_das"][1] += 1
    for i, item in enumerate(grammar.make_items(ctx, PROBES), 1):
        outcome = grammar.log(ctx, item, "placement", grammar.question(ctx, item, f"Grammar {i} of {PROBES}"))
        out["grammar"][0] += outcome == CORRECT
        out["grammar"][1] += 1
    return out
