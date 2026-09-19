"""Irregular verbs from the books: the past tense and the perfect, practised with the book sentence.

A verb joins once it has turned up in a paragraph the kid has read (most common verbs first). Each verb
has two cards, past ("ging") and perfect ("ist gegangen"), on the same spaced-repetition ladder as the
words. Misses come back at the end until they're right.
"""
from __future__ import annotations

from dataclasses import dataclass

from rich.panel import Panel
from rich.text import Text

from . import sfx, srs, ui
from .answers import ALMOST, CORRECT, WRONG, Check, _distance, normalize
from .content import Verb, VerbHit, trim_around
from .speaking import hear
from .ui import console, icon

KINDS = {"past": "Past tense", "perfect": "Perfect tense"}
NEXT_SECONDS = 2.0


@dataclass
class VerbResult:
    right: int = 0
    total: int = 0


def verb_progress(states: dict) -> str:
    """"12 started · 5 learned": a verb is learned when both its cards are."""
    verbs: dict[str, list[int]] = {}
    for key, s in states.items():
        verbs.setdefault(key.split("|")[0], []).append(s.get("box", 0))
    learned = sum(1 for boxes in verbs.values() if min(boxes) >= srs.LEARNED_BOX and len(boxes) == len(KINDS))
    return f"{len(verbs)} started · [good]{learned} learned[/]" if verbs else "[hint]none yet[/]"


def read_hits(ctx, inf: str) -> list[VerbHit]:
    """Sentences with this verb in paragraphs the kid has already read."""
    books = ctx.profile.data["books"]
    return [h for h in ctx.content.verb_hits.get(inf, []) if h.unit_n < books.get(h.book_id, {}).get("next", 1)]


def unlocked(ctx) -> list[str]:
    """Verbs met in the reading so far, the most common in the books first."""
    verbs = [inf for inf in ctx.content.verb_hits if inf in ctx.content.verbs and read_hits(ctx, inf)]
    return sorted(verbs, key=lambda inf: -len(ctx.content.verb_hits[inf]))


def plan(ctx, first_today: bool) -> list[str]:
    """Card keys ("gehen|past") for today: due ones, then new verbs (both cards) in the first warm-up."""
    states = ctx.profile.data["verbs"]
    today = ctx.today.isoformat()
    due = sorted((k for k, s in states.items() if s.get("box", 0) >= 1 and s.get("due") and s["due"] <= today
                  and k.split("|")[0] in ctx.content.verbs), key=lambda k: states[k]["due"])
    new = []
    if first_today:
        fresh = [inf for inf in unlocked(ctx) if f"{inf}|past" not in states]
        for inf in fresh[: int(ctx.settings["verbs_per_day"])]:
            new += [f"{inf}|past", f"{inf}|perfect"]
    return due + new


def check_form(answer: str, verb: Verb, kind: str, expected: str) -> Check:
    given, want = normalize(answer), normalize(expected)
    if kind == "perfect":
        given = " ".join(w for w in given.split() if w not in ("er", "sie", "es"))
    if given == want:
        return Check(CORRECT)
    if kind == "perfect":
        words = given.split()
        if words and words[-1] == normalize(verb.participle):
            if len(words) == 1:
                return Check(ALMOST, f"Add the helper verb: {verb.perfect}.")
            helper = "sein" if verb.helper == "ist" else "haben"
            return Check(ALMOST, f"The helper verb is {helper}: {verb.perfect}.")
    else:
        if given in {normalize(f) for f in verb.past_forms}:
            return Check(ALMOST, f"Right verb, but here it's {expected}.")
        if given.endswith("te") and given != want and not verb.past.endswith("te"):
            return Check(WRONG, f"{verb.inf} is irregular: {verb.past}, not +te.")
    if len(want) >= 4 and _distance(given, want) == 1:
        return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)


def _cloze(hit: VerbHit) -> tuple[str, str]:
    """(sentence with the form blanked out, the form)."""
    sentence = trim_around(hit.sentence, hit.form)
    words = sentence.split()
    for i, w in enumerate(words):
        core = w.strip(".,;:!?»«„“”\"'()–-")
        if core.lower() == hit.form.lower():
            words[i] = w.replace(core, "_____", 1)
            return " ".join(words), core
    return sentence, hit.form


def card(ctx, key: str, heading: str, repeat: bool = False) -> str:
    """One question. Returns CORRECT, ALMOST or WRONG."""
    inf, kind = key.split("|")
    verb = ctx.content.verbs[inf]
    hits = [h for h in read_hits(ctx, inf) if h.kind == kind] or read_hits(ctx, inf)
    hit = ctx.rng.choice(hits) if hits else None
    books = {b.id: b for b in ctx.content.books}

    ui.clear()
    ui.title(f"{ctx.step}{heading}", "just for practice, no score" if repeat else "irregular verbs from your books")
    console.print(Panel(Text.assemble((verb.inf, "de.word"), ("  ·  " + verb.en, "en")), title=KINDS[kind],
                        border_style="cyan", padding=(1, 2)))
    expected = verb.past if kind == "past" else verb.perfect
    if kind == "past" and hit and hit.kind == "past":
        blanked, expected = _cloze(hit)
        console.print(Panel(Text(blanked, style="italic cyan"), title=f"In the book · {books[hit.book_id].short_title}",
                            border_style="magenta", padding=(0, 2)))
        prompt = "Fill the gap (past tense):"
    elif kind == "past":
        prompt = "er/sie/es … (past tense):"
    else:
        console.print("[hint]Helper verb (hat / ist) + past participle, e.g. hat gesehen.[/]")
        prompt = "er/sie/es … (perfect):"
    console.print(ui.umlaut_tip())
    answer = ui.ask_answer(prompt)

    check = check_form(answer, verb, kind, expected) if answer else Check(WRONG)
    if not answer:
        console.print(f"[hint]Here it is: {ui.escape(expected)}[/]")
    else:
        style, label = {CORRECT: ("good", f"{icon('ok')} Correct!"), ALMOST: ("almost", f"{icon('almost')} Almost"),
                        WRONG: ("bad", f"{icon('bad')} Not quite")}[check.outcome]
        console.print(f"[{style}]{label}[/] {ui.escape(check.message or '')}")
        sfx.play(ctx.audio, {CORRECT: "right", ALMOST: "almost", WRONG: "wrong"}[check.outcome])
    forms = Text.assemble((verb.inf, "de.word"), "  –  ", (verb.past, "de.word"), "  –  ", (verb.perfect, "de.word"))
    console.print(Panel(forms, title="The forms", border_style="green" if check.outcome == CORRECT else "red",
                        padding=(0, 2)))
    if hit:
        console.print(Text.assemble(("in the book: ", "hint"), (trim_around(hit.sentence, hit.form), "italic cyan")))
    hear(ctx, f"{verb.inf}. {verb.past}. {verb.perfect}.")
    if check.outcome == CORRECT:
        console.print("[hint]Next one in a moment… (Enter = go now)[/]")
        ui.pause(NEXT_SECONDS, skippable=True)
    else:
        options = {"": "next"}
        if ctx.audio.can_speak:
            options["r"] = "hear the forms again"
        while ui.keys(options) == "r":
            hear(ctx, f"{verb.inf}. {verb.past}. {verb.perfect}.")
    return check.outcome


def run_verbs(ctx, first_today: bool) -> VerbResult:
    """Today's verb cards (graded, on the ladder), then misses again until right (practice only)."""
    result = VerbResult()
    keys = plan(ctx, first_today)
    if not keys:
        return result
    states = ctx.profile.data["verbs"]
    ctx.rng.shuffle(keys)
    not_yet = []
    for i, key in enumerate(keys, 1):
        outcome = card(ctx, key, f"Verb forms {i} of {len(keys)}")
        srs.apply_result(states.setdefault(key, srs.new_state()), outcome, ctx.today)
        result.total += 1
        result.right += outcome == CORRECT
        if outcome != CORRECT:
            not_yet.append(key)
        ctx.profile.count(ctx.today, verbs=1, verbs_right=int(outcome == CORRECT))
        ctx.profile.save()
    round_no = 0
    while not_yet:
        round_no += 1
        ctx.rng.shuffle(not_yet)
        not_yet = [key for i, key in enumerate(not_yet, 1)
                   if card(ctx, key, f"Verbs again until they stick · round {round_no} · {i} of {len(not_yet)}",
                           repeat=True) != CORRECT]
    return result
