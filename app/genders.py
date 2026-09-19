"""der, die or das? A quick drill on the nouns the kid has already started, on the words' ladder.

A noun joins once its word has been answered in the warm-up (most common first). Misses come back at the
end until they're right. A wrong answer shows the ending rule when there is one (-ung is always die).
"""
from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from . import sfx, srs, ui
from .answers import CORRECT, WRONG, normalize
from .speaking import hear
from .ui import console, icon
from .verbs import NEXT_SECONDS, VerbResult

ARTICLES = ("der", "die", "das")
CHOICES = {"1": "der", "2": "die", "3": "das"}

# (endings, article, how sure): shown after a wrong answer when the noun follows the rule.
RULES = [
    (("ung", "heit", "keit", "schaft"), "die", "always"),
    (("chen", "lein"), "das", "always"),
    (("ion", "tät", "ik", "ei", "ie", "ur", "enz", "anz", "ade", "age", "ette"), "die", "usually"),
    (("ment", "um", "ma", "nis", "tum"), "das", "usually"),
    (("ling", "ismus", "or", "ig", "ich", "ant", "ent", "ist", "eur"), "der", "usually"),
    (("e",), "die", "often"),
]


def gender_progress(states: dict) -> str:
    """"40 started · 12 learned"."""
    learned = sum(1 for s in states.values() if s.get("box", 0) >= srs.LEARNED_BOX)
    return f"{len(states)} nouns started · [good]{learned} learned[/]" if states else "[hint]none yet[/]"


def split(de: str) -> tuple[str, str] | None:
    """('der', 'Tisch') for a single noun with one clear gender, else None."""
    parts = de.split()
    if len(parts) != 2 or parts[0] not in ARTICLES:
        return None
    return parts[0], parts[1]


def eligible(word) -> bool:
    """A noun with one gender and a singular (not die Eltern, not der/das Joghurt)."""
    if word.pos != "noun" or not split(word.de):
        return False
    article, noun = split(word.de)
    if word.plural and normalize(word.plural) == normalize(word.de):
        return False  # plural only: die Leute
    if "plural" in word.note.lower() and "only" in word.note.lower():
        return False
    return not any(alt.split()[-1] == noun and alt.split()[0] != article for alt in word.de_alt if split(alt))


def rule_tip(noun: str, article: str) -> str:
    for endings, rule_article, sure in RULES:
        ending = next((e for e in endings if noun.lower().endswith(e)), None)
        if ending and rule_article == article:
            return f"Tip: nouns ending in -{ending} are {sure} {article}."
    return ""


def plan(ctx, first_today: bool) -> list[str]:
    """Word ids for today: due ones, then (in the day's first warm-up) nouns started but not drilled yet."""
    states, vocab, words = ctx.profile.data["genders"], ctx.profile.data["vocab"], ctx.content.words
    today = ctx.today.isoformat()
    due = sorted((wid for wid, s in states.items()
                  if wid in words and s.get("box", 0) >= 1 and s.get("due") and s["due"] <= today),
                 key=lambda wid: states[wid]["due"])
    new = []
    if first_today:
        started = [w for wid, s in vocab.items() if s.get("box", 0) >= 1 and wid not in states
                   and (w := words.get(wid)) and eligible(w)]
        new = [w.id for w in sorted(started, key=lambda w: (w.rank, w.id))][: int(ctx.settings["genders_per_day"])]
    return due + new


def card(ctx, word, heading: str, repeat: bool = False) -> str:
    """One noun: der, die or das? Returns CORRECT or WRONG."""
    article, noun = split(word.de)
    ui.clear()
    ui.title(f"{ctx.step}{heading}", "just for practice, no score" if repeat else "der, die or das?")
    ui.todo("type", what="Choose der, die or das: type 1, 2 or 3 (or the word).")
    console.print(Panel(Text.assemble(("___ ", "de.word"), (noun, "de.word"), ("  ·  " + ", ".join(word.en[:2]), "en")),
                        border_style="cyan", padding=(1, 2)))
    while True:
        answer = ui.ask_answer("1 der · 2 die · 3 das:").lower()
        chosen = CHOICES.get(answer, answer if answer in ARTICLES else "" if answer else "?")
        if chosen:
            break
        console.print("[warn]Type 1, 2 or 3 (or der, die, das).[/]")
    right = chosen == article
    plural = f", {word.plural}" if word.plural and word.plural != "—" else ""
    if right:
        console.print(f"[good]{icon('ok')} Correct![/]")
        sfx.play(ctx.audio, "right")
    else:
        console.print(f"[bad]{icon('bad')} Not quite.[/]" if chosen != "?" else "[hint]Here it is:[/]")
        sfx.play(ctx.audio, "wrong")
    console.print(Panel(Text(word.de + plural, style="de.word"), border_style="green" if right else "red",
                        padding=(0, 2)))
    if not right and (tip := rule_tip(noun, article)):
        console.print(f"[note]{tip}[/]")
    hear(ctx, word.de)
    if right:
        console.print("[hint]Next one in a moment… (Enter = go now)[/]")
        ui.pause(NEXT_SECONDS, skippable=True)
    else:
        ui.keys({"": "next"})
    return CORRECT if right else WRONG


def run_genders(ctx, first_today: bool) -> VerbResult:
    """Today's noun genders, graded and on the ladder. Misses go into result.missed for repeat_genders()."""
    result = VerbResult()
    ids = [wid for wid in plan(ctx, first_today) if eligible(ctx.content.words[wid])]
    states = ctx.profile.data["genders"]
    ctx.rng.shuffle(ids)
    for i, wid in enumerate(ids, 1):
        outcome = card(ctx, ctx.content.words[wid], f"der, die, das {i} of {len(ids)}")
        srs.apply_result(states.setdefault(wid, srs.new_state()), outcome, ctx.today)
        result.total += 1
        result.right += outcome == CORRECT
        if outcome != CORRECT:
            result.missed.append(wid)
        ctx.profile.count(ctx.today, genders=1, genders_right=int(outcome == CORRECT))
        ctx.profile.save()
    return result


def repeat_genders(ctx, not_yet: list[str]) -> None:
    """Missed genders again, round after round, until each is right (practice only, no score)."""
    not_yet = list(not_yet)
    round_no = 0
    while not_yet:
        round_no += 1
        ctx.rng.shuffle(not_yet)
        not_yet = [wid for i, wid in enumerate(not_yet, 1)
                   if card(ctx, ctx.content.words[wid],
                           f"der, die, das again until they stick · round {round_no} · {i} of {len(not_yet)}",
                           repeat=True) != CORRECT]
