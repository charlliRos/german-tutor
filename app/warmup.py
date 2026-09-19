"""Vocabulary warm-up: new-word cards, then a graded quiz with spaced repetition.

The daily warm-up grows from `warmup_start` words to `warmup_max` over about a year of practice.
It can be run again any time: later rounds that day are extra practice on words already started.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import sfx, srs, ui, verbs
from .answers import ALMOST, CORRECT, WRONG, Check, check_english, check_german, normalize
from .content import BANK_LABELS, Word, words_sharing_english
from .speaking import hear, speak_and_compare
from .ui import console, icon

AUTO_NEXT = "auto_next"  # quiz(): correct, and no key press needed to continue
ONCE_MORE = "once_more"  # quiz(): "my answer was right too": counts as correct, but comes back once more today
PASTED = Check(WRONG, "No pasting! This one comes back until you type it yourself.", overridable=False)
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
    verbs: verbs.VerbResult = field(default_factory=verbs.VerbResult)

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
        if word.example_en:
            grid.add_row("", Text(word.example_en, style="hint"))
    if word.story_de and word.story_de != word.example_de:
        grid.add_row("in the book", Text(word.story_de, style="italic cyan"))
        grid.add_row("", Text(word.story_from, style="hint"))
    return grid


def _listen_options(ctx, word: Word, options: dict[str, str]) -> str:
    """Show options (plus replay ones when audio works); handle replays; return the other choice."""
    if ctx.audio.can_speak:
        options = {**options, "r": "hear again", "s": "say it myself"}
        if word.example_de:
            options["e"] = "hear the example"
        if word.story_de and word.story_de != word.example_de:
            options["b"] = "hear the book sentence"
    while True:
        choice = ui.keys(options)
        if choice == "r":
            hear(ctx, word.de)
        elif choice == "s":
            speak_and_compare(ctx, word.de)
        elif choice == "e":
            hear(ctx, word.example_de, slow=False)
        elif choice == "b":
            hear(ctx, word.story_de.strip("… "), slow=False)
        else:
            return choice


def show_card(ctx, word: Word, i: int, total: int) -> None:
    ui.clear()
    ui.title(f"{ctx.step}New word {i} of {total}", f"{BANK_LABELS.get(word.bank, word.bank)} · {word.topic}")
    ui.todo("memorise", what="Learn this word. No typing yet: that comes after the new words.")
    console.print(Panel(word_details(word), border_style="magenta", padding=(1, 2)))
    hear(ctx, word.de)
    if ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
        ui.todo("say", what=f"{icon('mic')} Now repeat the word after Fritz.")
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
    pastes = ui.paste_count()
    if direction == "en2de":
        ui.todo("type", what="Type the German word." + (" Include der / die / das." if word.pos == "noun" else ""))
        console.print(Panel(Text(", ".join(word.en[:2]), style="bold green"), title="English → German",
                            subtitle=POS_HINTS.get(word.pos, "") or None, border_style="green", padding=(1, 2)))
        console.print(ui.umlaut_tip())
        answer = ui.ask_answer("German:")
        check = _synonym_check(ctx, answer, word, check_german(answer, word))
    else:
        ui.todo("type", what="Type what it means in English.")
        console.print(ui.german(word.de, "German → English", word=True))
        hear(ctx, word.de)
        answer = ui.ask_answer("English:")
        check = check_english(answer, word)
    if ui.paste_count() > pastes:
        check = PASTED
        ctx.profile.count(ctx.today, caught=1)

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
        console.print("[good]OK, counted as correct.[/] [hint]It comes back once more at the end.[/]")
        sfx.play(ctx.audio, "right")
        return ONCE_MORE
    return check.outcome


def read_aloud(ctx, word: Word) -> None:
    ui.todo("say", what="Say this word out loud. Nothing to type.")
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
    states = ctx.profile.data["vocab"]
    plan = srs.plan_session(states, words, ctx.settings, ctx.today, size, new_allowed)
    # Key words of paragraphs already read come on top, in the day's first warm-up: new ones as new words,
    # known ones once more (extra practice) even if they aren't due.
    reading_queue = ctx.profile.data["reading_words"]
    if not ctx.profile.data.get("reading_words_filled"):  # profiles from before: their paragraphs' words too
        books = ctx.profile.data["books"]
        for book in ctx.content.books:
            for unit in book.units:
                if unit.kind == "text" and unit.n < books.get(book.id, {}).get("next", 1):
                    reading_queue.extend(wid for wid in unit.word_ids if wid not in reading_queue)
        ctx.profile.data["reading_words_filled"] = True
    reading_queue[:] = [wid for wid in reading_queue if wid in words]
    from_reading = srs.reading_words_due(words, reading_queue, int(ctx.settings["reading_words_per_day"])
                                         if first_today else 0)
    fresh = [wid for wid in from_reading if states.get(wid, {}).get("box", 0) == 0]
    again = [wid for wid in from_reading if wid not in fresh]
    plan.new = fresh + [wid for wid in plan.new if wid not in fresh]
    plan.reviews = [wid for wid in plan.reviews if wid not in again]
    plan.practice = [wid for wid in plan.practice if wid not in again]
    if plan.total + len(again) == 0:
        console.print("[warn]Nothing to practise yet. Do a normal warm-up first.[/]")
        return None

    result = WarmupResult(extra_practice=not first_today)
    not_yet: list[Word] = []  # wrong or almost: they come back until they're right
    ui.clear()
    ui.title(f"{ctx.step}{'Extra practice' if result.extra_practice else 'Warm-up'}",
             ui.plural(plan.total + len(again), "word"))
    parts = [f"{len(plan.new)} new" + (f" ({len(fresh)} from your reading)" if fresh else ""),
             f"{len(plan.reviews)} to review", f"{len(plan.practice)} to strengthen",
             f"{len(again)} again from your reading"]
    console.print(" · ".join(p for p in parts if not p.startswith("0 ")))
    console.print(("First you [bold]memorise[/] the new words (no typing), then you [bold]type[/] every word."
                   if plan.new else "You [bold]type[/] every word.")
                  + " Each screen says what to do at the top.")
    if result.extra_practice:
        console.print("[hint]You've already done today's warm-up, so this round is extra practice: "
                      "words you miss come back sooner, words you know stay on schedule.[/]")
    console.print(ui.umlaut_tip())
    ui.keys({"": "start"})
    for i, wid in enumerate(plan.new, 1):
        show_card(ctx, words[wid], i, len(plan.new))

    queue = ([(wid, "new") for wid in plan.new] + [(wid, "review") for wid in plan.reviews]
             + [(wid, "practice") for wid in plan.practice] + [(wid, "reading") for wid in again])
    ctx.rng.shuffle(queue)
    for pos, (wid, kind) in enumerate(queue, 1):
        word, state = words[wid], ctx.profile.word_state(wid)
        auto = None
        ui.clear()  # a fresh screen per question, so earlier cards and answers can't be copied
        sub = ("from your reading" if wid in from_reading
               else "a word to strengthen" if kind == "practice" else "")
        ui.title(f"{ctx.step}Word {pos} of {len(queue)}", sub)
        if kind != "new" and ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
            read_aloud(ctx, word)
            if kind == "review":
                srs.mark_practised(state, ctx.today)
            result.spoken += 1
        else:
            outcome = auto = quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")))
            if outcome == ONCE_MORE:
                not_yet.append(word)  # an answer the app didn't know: one more go, so it can't skip a word
            if outcome in (AUTO_NEXT, ONCE_MORE):
                outcome = CORRECT
            (srs.apply_practice if kind in ("practice", "reading") else srs.apply_result)(state, outcome, ctx.today)
            result.correct += outcome == CORRECT
            result.almost += outcome == ALMOST
            if outcome == WRONG:
                result.to_practise.append(word)
            if outcome != CORRECT:
                not_yet.append(word)
            ctx.profile.count(ctx.today, words=1, right=int(outcome == CORRECT), almost=int(outcome == ALMOST),
                              new=int(kind == "new"))
        if wid in reading_queue:
            reading_queue.remove(wid)  # met again: done (it stays in the normal repetition schedule)
        ctx.profile.save()
        if auto == AUTO_NEXT:
            ui.pause(AUTO_NEXT_SECONDS, skippable=True)

    # Every word is graded: the warm-up counts now, even if they stop during the repeats.
    ctx.profile.count(ctx.today, warmups=1)
    ctx.profile.save()
    # Verbs are graded before the practice-only repeats, so stopping during the repeats loses nothing.
    result.verbs = verbs.run_verbs(ctx, first_today)
    repeat_until_right(ctx, not_yet)
    verbs.repeat_verbs(ctx, result.verbs.missed)
    return result


def repeat_until_right(ctx, words: list[Word]) -> None:
    """Missed words come back, shuffled, round after round until each one is answered right.
    Just for practice: the score and the schedule were already saved."""
    round_no = 0
    while words:
        round_no += 1
        ctx.rng.shuffle(words)
        missed = []
        for i, word in enumerate(words, 1):
            ui.clear()
            ui.title(f"{ctx.step}Again until it sticks · round {round_no} · {i} of {len(words)}",
                     "just for practice, no score")
            outcome = quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")), second_chance=True)
            if outcome == AUTO_NEXT:
                ui.pause(AUTO_NEXT_SECONDS, skippable=True)
            elif outcome != CORRECT:
                missed.append(word)
        words = missed
