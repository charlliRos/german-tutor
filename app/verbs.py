"""Irregular verbs from the books: the past tense and the perfect, practised with the book sentence.

A verb joins once it has turned up in a paragraph the kid has read (most common verbs first). Each verb
has two cards, past ("ging") and perfect ("ist gegangen"), on the same spaced-repetition ladder as the
words. Misses come back at the end until they're right.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.panel import Panel
from rich.text import Text

from . import attempts, sfx, srs, ui
from .answers import ALMOST, CORRECT, WRONG, Check, _distance, normalize
from .content import Verb, VerbHit, bare_word, person_forms, trim_around
from .speaking import hear
from .ui import console, icon

KINDS = {"past": "Past tense", "perfect": "Perfect tense"}
NEXT_SECONDS = 1.5   # after a right answer, then the next question starts by itself
WRONG_SECONDS = 4    # after a wrong one: time to read the right answer, then on by itself (a key stops it)
ONCE_MORE = "once_more"  # card(): "my answer was right too": counts as correct, but comes back once more today


PRONOUNS = {"ich", "du", "er", "sie", "es", "wir", "ihr", "man"}


@dataclass
class VerbResult:
    right: int = 0
    total: int = 0
    missed: list[str] = field(default_factory=list)  # card keys to repeat until right


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
    if first_today:  # a verb with a card missing (e.g. they stopped halfway) gets just that card
        fresh = [inf for inf in unlocked(ctx) if any(f"{inf}|{kind}" not in states for kind in KINDS)]
        for inf in fresh[: int(ctx.settings["verbs_per_day"])]:
            new += [f"{inf}|{kind}" for kind in KINDS if f"{inf}|{kind}" not in states]
    return due + [key for key in new if key not in due]


_OTHER_FORMS: dict[int, dict[str, str]] = {}


def other_forms(content) -> dict[str, str]:
    """Every listed verb form -> its infinitive, to tell a different verb from a typo (sank is singen)."""
    key = id(content)
    if key not in _OTHER_FORMS:
        forms: dict[str, str] = {}
        for v in content.verbs.values():
            for form in v.past_forms + [v.perfect, v.participle]:
                forms.setdefault(normalize(form), v.inf)
        _OTHER_FORMS[key] = forms
    return _OTHER_FORMS[key]


def check_form(answer: str, verb: Verb, kind: str, expected: str, others: dict[str, str] | None = None) -> Check:
    given = " ".join(w for w in normalize(answer).split() if w not in PRONOUNS)  # "er ging" = "ging"
    want = normalize(expected)
    if given == want:
        return Check(CORRECT)
    alt_perfect = {normalize(a) for a in verb.alt if a.split()[0] in ("hat", "ist")}
    alt_past = {normalize(f) for a in verb.alt if a.split()[0] not in ("hat", "ist") for f in person_forms(a)}
    if given in (alt_perfect if kind == "perfect" else alt_past):
        return Check(CORRECT, f"Also right. The book uses {expected}.")
    other = (others or {}).get(given)
    if other and other != verb.inf:
        return Check(WRONG, f"That's a form of {other}. Here we need {verb.inf}.")
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
        if given.endswith("te") and not verb.past.endswith("te") and not verb.alt:
            return Check(WRONG, f"{verb.inf} is irregular: {verb.past}, not +te.")
    if len(want) >= 4 and _distance(given, want) == 1:
        return Check(ALMOST, "Small spelling mistake.")
    return Check(WRONG)


def _cloze(hit: VerbHit) -> tuple[str, str] | None:
    """(sentence with the form blanked out, the form), or None if the form can't be found as a whole word."""
    sentence = trim_around(hit.sentence, hit.form)
    words = sentence.split()
    for i, w in enumerate(words):
        if bare_word(w) == hit.form.lower():
            start = w.lower().index(hit.form.lower())
            form = w[start:start + len(hit.form)]
            words[i] = w[:start] + "_____" + w[start + len(hit.form):]
            return " ".join(words), form
    return None


def card(ctx, key: str, heading: str, repeat: bool = False) -> str:
    """One question. Returns CORRECT, ALMOST, WRONG or ONCE_MORE."""
    inf, kind = key.split("|")
    verb = ctx.content.verbs[inf]
    hits = [h for h in read_hits(ctx, inf) if h.kind == kind] or read_hits(ctx, inf)
    hit = ctx.rng.choice(hits) if hits else None
    books = {b.id: b for b in ctx.content.books}

    ui.clear()
    expected = verb.past if kind == "past" else verb.perfect
    cloze = _cloze(hit) if kind == "past" and hit and hit.kind == "past" else None
    ui.title(f"{ctx.step}{heading}", "just for practice, no score" if repeat else "irregular verbs from your books")
    ui.todo("type", what="Type the past tense that fills the gap." if cloze else
            "Type the past tense (er/sie/es form)." if kind == "past" else
            "Type the perfect tense: hat or ist + past participle.")
    console.print(Panel(Text.assemble((verb.inf, "de.word"), ("  ·  " + verb.en, "en")), title=KINDS[kind],
                        border_style="cyan", padding=(1, 2)))
    if cloze:
        blanked, expected = cloze
        console.print(Panel(Text(blanked, style="italic cyan"), title=f"In the book · {books[hit.book_id].short_title}",
                            border_style="magenta", padding=(0, 2)))
        prompt = "Fill the gap (past tense):"
    elif kind == "past":
        prompt = "er/sie/es … (past tense):"
    else:
        console.print("[hint]Helper verb (hat / ist) + past participle, e.g. hat gemacht, ist gereist.[/]")
        prompt = "er/sie/es … (perfect):"
    console.print(ui.umlaut_tip())
    pastes = ui.paste_count()
    answer = ui.ask_answer(prompt)

    check = check_form(answer, verb, kind, expected, other_forms(ctx.content)) if answer else Check(WRONG)
    if ui.paste_count() > pastes:
        check = Check(WRONG, "No pasting! This one comes back until you type it yourself.", overridable=False)
        ctx.profile.count(ctx.today, caught=1)
        attempts.note(answer, WRONG, check.message, kind, pasted=True)
    else:
        attempts.note(answer, check.outcome, check.message, kind)
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
        if answer and not repeat and check.overridable:
            options["o"] = "my answer was right too"
        if ctx.audio.can_speak:
            options["r"] = "hear the forms again"
        choice = ui.timed_keys(options, WRONG_SECONDS)  # goes on by itself; a key stops the clock
        while choice == "r":
            hear(ctx, f"{verb.inf}. {verb.past}. {verb.perfect}.")
            choice = ui.keys(options)
        if choice == "o":
            console.print("[good]OK, counted as correct.[/] [hint]It comes back once more at the end.[/]")
            sfx.play(ctx.audio, "right")
            return ONCE_MORE
    return check.outcome


def log(ctx, key: str, context: str, outcome: str, scheduled: bool = False, claimed: bool = False) -> str:
    """Keep the answer in the answer log (attempts.py); returns the outcome."""
    inf, kind = key.split("|")
    verb = ctx.content.verbs[inf]
    attempts.record(ctx.profile, ctx.today, item=key, item_version=attempts.version(verb.inf, kind, verb.past,
                                                                                   verb.perfect, sorted(verb.alt)),
                    competency="grammar.irregular_verbs", subcompetency=kind, context=context,
                    score=attempts.graded(outcome if outcome != ONCE_MORE else CORRECT), grader=attempts.GRADER,
                    schedule="result" if scheduled else None, store="verbs" if scheduled else None,
                    counted=outcome if scheduled else None, claimed_correct=claimed or None)
    return outcome


def run_verbs(ctx, first_today: bool) -> VerbResult:
    """Today's verb cards, graded and on the ladder. Misses go into result.missed for repeat_verbs()."""
    result = VerbResult()
    attempts.start(ctx.profile)
    keys = plan(ctx, first_today)
    states = ctx.profile.data["verbs"]
    ctx.rng.shuffle(keys)
    for i, key in enumerate(keys, 1):
        outcome = card(ctx, key, f"Verb forms {i} of {len(keys)}")
        if outcome == ONCE_MORE:
            result.missed.append(key)  # an answer the app didn't know: one more go, so it can't skip a card
            outcome = CORRECT
        srs.apply_result(states.setdefault(key, srs.new_state()), outcome, ctx.today)
        log(ctx, key, "verbs.due", outcome, scheduled=True, claimed=key in result.missed)
        result.total += 1
        result.right += outcome == CORRECT
        if outcome != CORRECT:
            result.missed.append(key)
        ctx.profile.count(ctx.today, verbs=1, verbs_right=int(outcome == CORRECT))
        ctx.profile.save()
    return result


def repeat_verbs(ctx, not_yet: list[str]) -> None:
    """Missed verb cards again, round after round, until each is right (practice only, no score)."""
    not_yet = list(not_yet)
    round_no = 0
    while not_yet:
        round_no += 1
        ctx.rng.shuffle(not_yet)
        not_yet = [key for i, key in enumerate(not_yet, 1)
                   if log(ctx, key, "verbs.repeat",
                          card(ctx, key, f"Verbs again until they stick · round {round_no} · {i} of {len(not_yet)}",
                               repeat=True)) != CORRECT]
