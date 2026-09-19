"""Vocabulary warm-up: new-word cards, then a graded quiz with spaced repetition.

The daily warm-up grows from `warmup_start` words to `warmup_max` over about a year of practice.
It can be run again any time: later rounds that day are extra practice on words already started.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import sfx, srs, ui
from .answers import ALMOST, CORRECT, WRONG, Check, check_english, check_german, normalize
from .content import BANKS, Word, words_sharing_english
from .speaking import hear, speak_and_compare
from .ui import console, icon

AUTO_NEXT = "auto_next"  # quiz(): correct, and no key press needed to continue
AUTO_NEXT_SECONDS = 2.0

POS_HINTS = {"noun": "noun: include der / die / das", "verb": "verb", "adj": "adjective", "adv": "adverb",
             "prep": "preposition", "conj": "conjunction", "pron": "pronoun", "num": "number",
             "phrase": "phrase", "other": ""}


@dataclass
class WarmupResult:
    extra_practice: bool = False
    correct: int = 0
    almost: int = 0
    to_practise: list[Word] = field(default_factory=list)
    spoken: int = 0

    @property
    def graded(self) -> int:
        return self.correct + self.almost + len(self.to_practise)


def word_details(word: Word) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="hint", justify="right")
    grid.add_column()
    grid.add_row("German", Text(word.de, style="de.word"))
    if word.pos == "noun" and word.plural and word.plural != "—":
        grid.add_row("plural", Text(word.plural, style="de"))
    grid.add_row("English", Text(", ".join(word.en), style="en"))
    if word.note:
        grid.add_row("note", Text(word.note, style="note"))
    if word.example_de:
        grid.add_row("example", Text(word.example_de, style="italic cyan"))
        grid.add_row("", Text(word.example_en, style="hint"))
    return grid


def _listen_options(ctx, word: Word, options: dict[str, str]) -> str:
    """Show options (plus replay ones when audio works); handle replays; return the other choice."""
    if ctx.audio.can_speak:
        options = {**options, "r": "hear again", "s": "say it myself"}
        if word.example_de:
            options["e"] = "hear the example"
    while True:
        choice = ui.keys(options)
        if choice == "r":
            hear(ctx, word.de)
        elif choice == "s":
            speak_and_compare(ctx, word.de)
        elif choice == "e":
            hear(ctx, word.example_de, slow=False)
        else:
            return choice


def show_card(ctx, word: Word, i: int, total: int) -> None:
    ui.clear()
    ui.title(f"{ctx.step}New word {i} of {total}", f"{BANKS.get(word.bank, word.bank)} · {word.topic}")
    console.print(Panel(word_details(word), border_style="magenta", padding=(1, 2)))
    hear(ctx, word.de)
    if ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
        console.print(f"[rec]{icon('mic')} Speaking turn:[/] [bold]repeat the word after Fritz.[/]")
        speak_and_compare(ctx, word.de)
    else:
        _listen_options(ctx, word, {"": "next"})
    ctx.profile.word_state(word.id)  # box stays 0 until the quiz grades it


def _synonym_check(ctx, answer: str, word: Word, check: Check) -> Check:
    if check.outcome != WRONG or not normalize(answer):
        return check
    for other in words_sharing_english(ctx.content, word):
        if normalize(answer) in {normalize(d) for d in (other.de, *other.de_alt)}:
            return Check(CORRECT, f"{other.de} means that too. We were thinking of {word.de}: good to know both!")
    return check


def quiz(ctx, word: Word, direction: str, second_chance: bool = False) -> str:
    if direction == "en2de":
        console.print(Panel(Text(", ".join(word.en[:2]), style="bold green"), title="English → German",
                            subtitle=POS_HINTS.get(word.pos, "") or None, border_style="green", padding=(1, 2)))
        console.print(ui.umlaut_tip())
        answer = ui.ask_answer("German:")
        check = _synonym_check(ctx, answer, word, check_german(answer, word))
    else:
        console.print(ui.german(word.de, "German → English", word=True))
        hear(ctx, word.de)
        answer = ui.ask_answer("English:")
        check = check_english(answer, word)

    if not answer:
        console.print("[hint]Here it is:[/]")
        style = "bad"
    else:
        style, label = {CORRECT: ("good", f"{icon('ok')} Correct!"), ALMOST: ("almost", f"{icon('almost')} Almost"),
                        WRONG: ("bad", f"{icon('bad')} Not quite")}[check.outcome]
        console.print(f"[{style}]{label}[/] {ui.escape(check.message)}")
        sfx.play(ctx.audio, {CORRECT: "right", ALMOST: "almost", WRONG: "wrong"}[check.outcome])
    border = {"good": "green", "almost": "dark_orange", "bad": "red"}[style]
    console.print(Panel(word_details(word), border_style=border, padding=(0, 2)))
    if direction == "en2de":
        hear(ctx, word.de)

    if check.outcome == CORRECT and ctx.settings.get("auto_next_on_correct", True):
        console.print("[hint]Next one in a moment… (Enter = go now)[/]")
        return AUTO_NEXT  # the caller saves the result first, then pauses a moment and goes straight on
    options = {"": "next"}
    if check.overridable and answer and not second_chance and check.outcome != CORRECT:
        options["o"] = "my answer was right too"
    if _listen_options(ctx, word, options) == "o":
        console.print("[good]OK, counted as correct.[/]")
        sfx.play(ctx.audio, "right")
        return CORRECT
    return check.outcome


def read_aloud(ctx, word: Word) -> None:
    console.print(ui.german(word.de, f"{icon('mic')} Speaking turn: read it out loud",
                            subtitle=", ".join(word.en), word=True))
    speak_and_compare(ctx, word.de)


def run_warmup(ctx) -> WarmupResult | None:
    words = ctx.content.words
    if not words:
        console.print("[warn]The vocabulary bank is empty. Add words to content/vocab/.[/]")
        return None
    today = ctx.profile.day(ctx.today)
    first_today = not today.get("warmups")
    size = srs.warmup_size(ctx.settings, ctx.profile.practice_days(ctx.today))
    new_allowed = max(0, srs.new_word_cap(ctx.settings, size) - today.get("new", 0)) if first_today else 0
    plan = srs.plan_session(ctx.profile.data["vocab"], words, ctx.settings, ctx.today, size, new_allowed)
    if plan.total == 0:
        console.print("[warn]Nothing to practise yet. Do a normal warm-up first.[/]")
        return None

    result = WarmupResult(extra_practice=not first_today)
    ui.clear()
    ui.title(f"{ctx.step}{'Extra practice' if result.extra_practice else 'Warm-up'}", ui.plural(plan.total, "word"))
    parts = [f"{len(plan.new)} new", f"{len(plan.reviews)} to review", f"{len(plan.practice)} to strengthen"]
    console.print(" · ".join(p for p in parts if not p.startswith("0 ")))
    if result.extra_practice:
        console.print("[hint]You've already done today's warm-up, so this round is extra practice: "
                      "words you miss come back sooner, words you know stay on schedule.[/]")
    console.print(ui.umlaut_tip())
    ui.keys({"": "start"})
    for i, wid in enumerate(plan.new, 1):
        show_card(ctx, words[wid], i, len(plan.new))

    queue = ([(wid, "new") for wid in plan.new] + [(wid, "review") for wid in plan.reviews]
             + [(wid, "practice") for wid in plan.practice])
    ctx.rng.shuffle(queue)
    for pos, (wid, kind) in enumerate(queue, 1):
        word, state = words[wid], ctx.profile.word_state(wid)
        auto = None
        ui.clear()  # a fresh screen per question, so earlier cards and answers can't be copied
        ui.title(f"{ctx.step}Word {pos} of {len(queue)}", "a word to strengthen" if kind == "practice" else "")
        if kind != "new" and ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
            read_aloud(ctx, word)
            if kind == "review":
                srs.mark_practised(state, ctx.today)
            result.spoken += 1
        else:
            outcome = auto = quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")))
            if outcome == AUTO_NEXT:
                outcome = CORRECT
            (srs.apply_practice if kind == "practice" else srs.apply_result)(state, outcome, ctx.today)
            result.correct += outcome == CORRECT
            result.almost += outcome == ALMOST
            if outcome == WRONG:
                result.to_practise.append(word)
            ctx.profile.count(ctx.today, words=1, right=int(outcome == CORRECT), almost=int(outcome == ALMOST),
                              new=int(kind == "new"))
        ctx.profile.save()
        if auto == AUTO_NEXT:
            ui.pause(AUTO_NEXT_SECONDS, skippable=True)

    # Every word is graded: the warm-up counts now, even if they stop during the second chances.
    ctx.profile.count(ctx.today, warmups=1)
    ctx.profile.save()
    for i, word in enumerate(result.to_practise, 1):
        ui.clear()
        ui.title(f"{ctx.step}Second chance {i} of {len(result.to_practise)}", "just for practice, no score")
        if quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")), second_chance=True) == AUTO_NEXT:
            ui.pause(AUTO_NEXT_SECONDS, skippable=True)
    return result
