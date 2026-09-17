"""Daily reading: one paragraph of a classic, explained, then a random exercise."""
from __future__ import annotations

from datetime import datetime

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import ui
from .content import Book, Unit
from .speaking import hear, speak_and_compare
from .ui import console

SELF_GRADES = {"1": "needs work", "2": "mostly right", "3": "nailed it"}


def current_book(ctx) -> Book | None:
    """The chosen book, or the next one that still has unread paragraphs."""
    books = ctx.content.books
    ids = [b.id for b in books]
    start = ids.index(ctx.profile.data["current_book"]) if ctx.profile.data["current_book"] in ids else 0
    for book in books[start:] + books[:start]:
        if ctx.profile.book_state(book.id)["next"] <= len(book.units):
            return book
    return None


def _replay_until_enter(ctx, text: str, enter_label: str) -> None:
    options = {"": enter_label}
    if ctx.audio.can_speak:
        options["r"] = "hear the German again"
    while ui.keys(options) == "r":
        hear(ctx, text, slow=False)


def _key_words(unit: Unit) -> Table:
    table = Table(title="Key words", title_justify="left", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="green")
    table.add_column(style="dim")
    for w in unit.words:
        table.add_row(w.get("de", ""), w.get("en", ""), w.get("note", ""))
    return table


def _explain(book: Book, unit: Unit) -> None:
    console.print(ui.english(unit.en, "What it means"))
    if unit.explain_en:
        console.print(Panel(Text(unit.explain_en), title="What's going on", border_style="yellow", padding=(1, 2)))
    if unit.words:
        console.print(_key_words(unit))


def _choose_task(ctx) -> str:
    weights = dict(ctx.settings["reading_tasks"])
    if not ctx.audio.can_speak:
        weights.pop("read_aloud", None)
    tasks = [t for t, w in weights.items() if w > 0] or ["de2en"]
    return ctx.rng.choices(tasks, weights=[weights.get(t, 1) for t in tasks])[0]


def _self_grade(ctx, german_text: str | None) -> str:
    console.print("How did you do? Compare honestly. This is for you, not a score.")
    options = dict(SELF_GRADES)
    if german_text and ctx.audio.can_speak:
        options["r"] = "hear the German"
    while True:
        choice = ui.keys(options)
        if choice != "r":
            return SELF_GRADES[choice]
        hear(ctx, german_text, slow=False)


def _translate(ctx, unit: Unit, direction: str) -> dict:
    console.clear()
    if direction == "de2en":
        ui.title("Your turn: translate into English")
        console.print(ui.german(unit.de, "German"))
        answer = ui.ask_multiline("Your English translation:")
        ui.side_by_side("Your translation", answer, "Reference translation", unit.en)
        grade = _self_grade(ctx, None)
    else:
        ui.title("Your turn: translate into German")
        console.print(ui.english(unit.en, "English"))
        console.print(ui.UMLAUT_TIP)
        answer = ui.ask_multiline("Your German translation:")
        ui.side_by_side("Your translation", answer, "Original German", unit.de)
        hear(ctx, unit.de, slow=False)
        grade = _self_grade(ctx, unit.de)
    return {"answer": answer, "self_grade": grade}


def lesson(ctx, book: Book) -> None:
    state = ctx.profile.book_state(book.id)
    unit = book.units[state["next"] - 1]

    # 1. Read and listen
    console.clear()
    ui.title(book.title, f"{book.author} · part {unit.n} of {len(book.units)}")
    if unit.n == 1 and book.intro_en:
        console.print(Panel(Text(book.intro_en), title="About this book", border_style="magenta", padding=(1, 2)))
    console.print(ui.german(unit.de))
    hear(ctx, unit.de, slow=False)
    _replay_until_enter(ctx, unit.de, "show me what it means")

    # 2. Explanation
    _explain(book, unit)
    _replay_until_enter(ctx, unit.de, "my turn")

    # 3. Random exercise
    task = _choose_task(ctx)
    entry = {"date": datetime.now().isoformat(timespec="minutes"), "book": book.id, "unit": unit.n, "task": task}
    if task == "read_aloud":
        console.clear()
        ui.title("Your turn: read it out loud")
        console.print(ui.german(unit.de))
        speak_and_compare(ctx, unit.de, long_text=True)
    else:
        entry.update(_translate(ctx, unit, task))

    state["next"] += 1
    ctx.profile.data["current_book"] = book.id
    ctx.profile.count(ctx.today, units=1)
    ctx.profile.save()
    ctx.profile.add_journal(entry)
    if state["next"] > len(book.units):
        console.print(f"[bold green]You finished {book.title}! Well done.[/]")


def run_reading(ctx) -> None:
    done = 0
    while True:
        book = current_book(ctx)
        if book is None:
            console.print("[green]You've read every paragraph we have! Ask for new texts.[/]")
            return
        lesson(ctx, book)
        done += 1
        if done >= ctx.settings["units_per_day"]:
            ui.title("Reading done")
            if ui.keys({"": "finish", "y": "one more paragraph"}) != "y":
                return
