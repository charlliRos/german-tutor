"""Daily vocabulary warm-up: new-word cards, then a graded quiz with spaced repetition."""
from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import srs, ui
from .answers import ALMOST, CORRECT, WRONG, Check, check_english, check_german, normalize
from .content import Word, words_sharing_english
from .speaking import hear, speak_and_compare
from .ui import console

VERDICTS = {CORRECT: ("green", "✔ Correct!"), ALMOST: ("yellow", "≈ Almost"), WRONG: ("red", "✘ Not quite")}


def word_details(word: Word) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()
    grid.add_row("German", Text(word.de, style="bold cyan"))
    if word.pos == "noun" and word.plural and word.plural != "—":
        grid.add_row("plural", Text(word.plural, style="cyan"))
    grid.add_row("English", Text(", ".join(word.en), style="green"))
    if word.note:
        grid.add_row("note", Text(word.note, style="yellow"))
    if word.example_de:
        grid.add_row("example", Text(word.example_de, style="italic cyan"))
        grid.add_row("", Text(word.example_en, style="dim"))
    return grid


def _listen_options(ctx, word: Word, options: dict[str, str]) -> str:
    """Show options (plus replay ones when audio works); handle replays; return the other choice."""
    if ctx.audio.can_speak:
        options = {**options, "r": "hear again"}
        if word.example_de:
            options["e"] = "hear the example"
    while True:
        choice = ui.keys(options)
        if choice == "r":
            hear(ctx, word.de)
        elif choice == "e":
            hear(ctx, word.example_de, slow=False)
        else:
            return choice


def show_card(ctx, word: Word, i: int, total: int) -> None:
    ui.clear()
    ui.title(f"New word {i} of {total}", f"{word.bank} · {word.topic}")
    console.print(Panel(word_details(word), border_style="magenta", padding=(1, 2)))
    hear(ctx, word.de)
    if ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
        console.print("[bold red]🎤 Speaking turn:[/] [bold]repeat the word after Fritz.[/]")
        speak_and_compare(ctx, word.de)
    else:
        if ctx.audio.can_speak:
            console.print("[dim]👂 Just listen to this one (no speaking).[/]")
        _listen_options(ctx, word, {"": "next"})
    ctx.profile.word_state(word.id)  # box stays 0 until the quiz grades it
    ctx.profile.count(ctx.today, new=1)
    ctx.profile.save()


def _synonym_check(ctx, answer: str, word: Word, check: Check) -> Check:
    if check.outcome != WRONG or not normalize(answer):
        return check
    for other in words_sharing_english(ctx.content, word):
        if normalize(answer) in {normalize(d) for d in (other.de, *other.de_alt)}:
            return Check(ALMOST, f"{other.de} also means that! This time we're looking for {word.de}.")
    return check


def quiz(ctx, word: Word, direction: str) -> str:
    if direction == "en2de":
        hint = "noun: include der / die / das" if word.pos == "noun" else word.pos
        console.print(Panel(Text(", ".join(word.en[:2]), style="bold green"),
                            title="English → German", subtitle=hint, border_style="green", padding=(1, 2)))
        answer = ui.ask("German:")
        check = _synonym_check(ctx, answer, word, check_german(answer, word))
    else:
        console.print(ui.german(word.de, "German → English"))
        hear(ctx, word.de)
        answer = ui.ask("English:")
        check = check_english(answer, word)

    color, label = VERDICTS[check.outcome]
    console.print(f"[bold {color}]{label}[/] {check.message}")
    console.print(Panel(word_details(word), border_style=color, padding=(0, 2)))
    if direction == "en2de":
        hear(ctx, word.de)

    options = {"": "next"}
    if check.outcome != CORRECT:
        options["o"] = "my answer was right too"
    if _listen_options(ctx, word, options) == "o":
        console.print("[green]OK, counted as correct.[/]")
        return CORRECT
    return check.outcome


def read_aloud(ctx, word: Word) -> None:
    console.print(ui.german(word.de, "🎤 Speaking turn: read it out loud", subtitle=", ".join(word.en)))
    speak_and_compare(ctx, word.de)


def run_warmup(ctx) -> None:
    words = ctx.content.words
    if not words:
        console.print("[yellow]The vocabulary bank is empty. Add words to content/vocab/.[/]")
        return
    states = ctx.profile.data["vocab"]
    reviews, new = srs.plan_session(states, words, ctx.settings, ctx.today,
                                    new_so_far=ctx.profile.day(ctx.today).get("new", 0))
    if not reviews and not new:
        console.print("[green]No words due today. You're all caught up![/]")
        return

    ui.clear()
    ui.title("Warm-up", f"{len(new)} new · {len(reviews)} to review")
    console.print(ui.UMLAUT_TIP)
    ui.keys({"": "start"})
    for i, wid in enumerate(new, 1):
        show_card(ctx, words[wid], i, len(new))

    queue = new + reviews
    ctx.rng.shuffle(queue)
    graded = right = 0
    missed: list[Word] = []
    for pos, wid in enumerate(queue, 1):
        word, state = words[wid], ctx.profile.word_state(wid)
        ui.clear()  # a fresh screen per question, so earlier cards and answers can't be copied
        ui.title(f"Word {pos} of {len(queue)}")
        if state["box"] >= 1 and ctx.audio.can_speak and ctx.rng.random() < ctx.settings["speak_chance"]:
            read_aloud(ctx, word)
            srs.mark_practised(state, ctx.today)
        else:
            outcome = quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")))
            srs.apply_result(state, outcome, ctx.today)
            graded += 1
            right += outcome == CORRECT
            ctx.profile.count(ctx.today, words=1, right=int(outcome == CORRECT))
            if outcome != CORRECT:
                missed.append(word)
        ctx.profile.save()

    if missed:
        for word in missed:
            ui.clear()
            ui.title("Second chance", "the ones you missed, just for practice")
            quiz(ctx, word, ctx.rng.choice(("en2de", "de2en")))

    ui.clear()
    ui.title("Warm-up done")
    if graded:
        console.print(f"[bold]{right} of {graded}[/] correct.  "
                      f"Streak: [bold]{ctx.profile.streak(ctx.today)}[/] day(s).")
