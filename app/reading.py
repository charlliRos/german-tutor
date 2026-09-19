"""Daily reading: the next paragraph of a classic, explained, with a random exercise."""
from __future__ import annotations

from datetime import datetime

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import ui
from .content import Book, Unit
from .speaking import hear, speak_and_compare
from .ui import QuitSession, console, icon

SELF_GRADES = {"1": "needs work", "2": "mostly right", "3": "nailed it"}


def current_book(ctx) -> Book | None:
    """The chosen book, or the next one that still has unread paragraphs."""
    books = ctx.content.books
    ids = [b.id for b in books]
    start = ids.index(ctx.profile.data["current_book"]) if ctx.profile.data["current_book"] in ids else 0
    for book in books[start:] + books[:start]:
        if book.next_unit(ctx.profile.book_state(book.id)["next"]) is not None:
            return book
    return None


def choose_book(ctx) -> str:
    """Pick the book to read. Returns a short message for the menu ("" if nothing changed)."""
    books = ctx.content.books
    narrow = console.width < 70
    ui.title("Choose a book")
    table = Table(caption=f"{icon('current')} = reading now", caption_justify="left")
    for col in ("#", "Title") + (() if narrow else ("Author", "Level")) + ("Paragraphs read",):
        table.add_column(col)
    for i, b in enumerate(books, 1):
        nxt = ctx.profile.book_state(b.id)["next"]
        read = f"{icon('done')} finished" if b.finished(nxt) else f"{b.parts_read(nxt)} of {b.parts}"
        mark = f" {icon('current')}" if b.id == ctx.profile.data["current_book"] else ""
        table.add_row(str(i), b.short_title + mark, *(() if narrow else (b.author, b.level)), read)
    console.print(table)
    while True:
        answer = ui.ask("Book number (Enter to keep the current one):")
        if not answer:
            return ""
        if not (answer.isdigit() and 1 <= int(answer) <= len(books)):
            console.print(f"[warn]'{ui.escape(answer)}' isn't a book number. Pick 1–{len(books)}, "
                          "or press Enter.[/]")
            continue
        book = books[int(answer) - 1]
        state = ctx.profile.book_state(book.id)
        if book.finished(state["next"]):
            console.print(f"You've already finished {book.short_title}.")
            if ui.keys({"y": "read it again from the start", "": "pick another book"}) != "y":
                continue
            state["next"] = 1
        ctx.profile.data["current_book"] = book.id
        ctx.profile.save()
        return f"[good]Now reading: {ui.escape(book.short_title)}[/]"


def _replay_until_enter(ctx, text: str, enter_label: str) -> None:
    options = {"": enter_label}
    if ctx.audio.can_speak:
        options["r"] = "hear the German again"
        options["s"] = "read it out loud myself"
    while (choice := ui.keys(options)) != "":
        if choice == "r":
            hear(ctx, text, slow=False)
        else:
            speak_and_compare(ctx, text, long_text=True)


def _explain(unit: Unit) -> None:
    console.print(ui.english(unit.en, "What it means"))
    if unit.explain_en:
        console.print(Panel(Text(unit.explain_en), title="What's going on", border_style="magenta", padding=(1, 2)))
    if unit.words:
        console.print(ui.key_words(unit.words))


def _choose_task(ctx) -> str:
    weights = dict(ctx.settings["reading_tasks"])
    if not ctx.audio.can_speak:
        weights.pop("read_aloud", None)
    usable = {t: w for t, w in weights.items() if w > 0} or {"de2en": 1, "en2de": 1}
    return ctx.rng.choices(list(usable), weights=list(usable.values()))[0]


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


def _translate(ctx, book: Book, unit: Unit, direction: str, entry: dict) -> None:
    """Fills entry with the answer (straight away, so quitting at the self-grade keeps it) and the grade."""
    to_english = direction == "de2en"
    reference = unit.en if to_english else unit.de
    ui.clear()
    ui.title(f"{ctx.step}Your turn: translate into {'English' if to_english else 'German'}", book.short_title)
    if to_english:
        console.print(ui.german(unit.de, "German"))
    else:
        console.print(ui.english(unit.en, "English"))
        if unit.words:
            console.print(ui.key_words(unit.words))
        console.print(ui.umlaut_tip())
    answer = ui.ask_multiline(f"Your {'English' if to_english else 'German'} translation:")
    if not answer:  # typed ? : show the answer, the task counts as skipped
        console.print(Panel(Text(reference, style="en" if to_english else "de"),
                            title="Reference translation" if to_english else "Original German",
                            border_style="green" if to_english else "cyan", padding=(1, 2)))
        if not to_english:
            hear(ctx, unit.de, slow=False)
        entry.update(answer="", skipped=True)
        ui.keys({"": "continue"})
        return
    entry.update(answer=answer, self_grade="not graded")
    ui.side_by_side("Your translation", answer,
                    "Reference translation" if to_english else "Original German", reference)
    if not to_english:
        hear(ctx, unit.de, slow=False)
    entry["self_grade"] = _self_grade(ctx, None if to_english else unit.de)


def _story_so_far(ctx, book: Book, state: dict) -> Unit | None:
    """Show English summaries of skipped parts; return the next German unit (None if the book ended)."""
    while True:
        unit = book.next_unit(state["next"])
        if unit is None or unit.kind == "text":
            return unit
        ui.clear()
        ui.title(f"{ctx.step}{book.short_title}", "the story continues")
        console.print(Panel(Text(unit.en), title="Meanwhile in the story…", subtitle=unit.covers or None,
                            border_style="magenta", padding=(1, 2)))
        state["next"] = unit.n + 1
        ctx.profile.save()
        ui.keys({"": "continue"})


def _celebrate(ctx, book: Book) -> None:
    ui.clear()
    text = Text(justify="center")
    text.append(f"{icon('party')}  You finished {book.title}!  {icon('party')}\n\n", style="good")
    text.append(f"{book.author} · {ui.plural(book.parts, 'paragraph')} read in German\n", style="en")
    text.append("Du hast das ganze Buch gelesen. Toll gemacht!", style="de")
    console.print(Panel(text, border_style="green", padding=(1, 4)))
    ui.keys({"": "choose my next book"})
    ui.clear()
    console.print(choose_book(ctx))


def _finish_lesson(ctx, book: Book, state: dict, unit: Unit, entry: dict) -> bool:
    """Move on to the next paragraph and keep the journal entry. True if it counts as read (not skipped)."""
    counted = not entry.get("skipped")
    state["next"] = unit.n + 1
    ctx.profile.data["current_book"] = book.id
    if counted:
        ctx.profile.count(ctx.today, units=1)
    ctx.profile.save()
    ctx.profile.add_journal(entry)
    return counted


def lesson(ctx, book: Book) -> bool:
    """One paragraph. Returns True if it counts as read (not skipped)."""
    state = ctx.profile.book_state(book.id)
    if state["next"] == 1 and book.intro_en:
        ui.clear()
        ui.title(f"{ctx.step}{book.short_title}", book.author)
        console.print(Panel(Text(book.intro_en), title="About this book", border_style="magenta", padding=(1, 2)))
        ui.keys({"": "start reading"})
    unit = _story_so_far(ctx, book, state)
    if unit is None:
        _celebrate(ctx, book)
        return False

    task = _choose_task(ctx)
    header = f"{ctx.step}Paragraph {unit.part} of {book.total_parts} · {book.short_title}"

    # 1. Read and listen
    ui.clear()
    ui.title(header, book.author)
    console.print(ui.german(unit.de))
    hear(ctx, unit.de, slow=False)

    entry = {"date": datetime.now().isoformat(timespec="minutes"), "book": book.id, "unit": unit.part, "task": task}
    try:
        if task == "de2en":
            # Translate first, so the English meaning isn't on screen just before.
            _replay_until_enter(ctx, unit.de, "translate it")
            _translate(ctx, book, unit, task, entry)
            ui.clear()
            ui.title(header, "what it means")
            console.print(ui.german(unit.de))
            _explain(unit)
            _replay_until_enter(ctx, unit.de, "done")
        else:
            _replay_until_enter(ctx, unit.de, "show me what it means")
            _explain(unit)
            _replay_until_enter(ctx, unit.de, "my turn")
            if task == "read_aloud":
                ui.clear()
                ui.title(f"{ctx.step}Your turn: read it out loud", book.short_title)
                console.print(ui.german(unit.de))
                speak_and_compare(ctx, unit.de, long_text=True)
            else:
                _translate(ctx, book, unit, task, entry)
    except QuitSession:
        if "answer" in entry:  # the translation is typed: keep it, and the paragraph counts as done
            _finish_lesson(ctx, book, state, unit, entry)
        raise

    counted = _finish_lesson(ctx, book, state, unit, entry)
    if book.finished(state["next"]):
        _story_so_far(ctx, book, state)  # a closing summary, if the book ends with one
        _celebrate(ctx, book)
    return counted


def run_reading(ctx) -> int:
    """Paragraphs until the daily amount is reached (and more if wanted). Returns paragraphs read."""
    done = lessons = 0
    while True:
        book = current_book(ctx)
        if book is None:
            console.print("[good]You've read every paragraph we have! Ask for new texts.[/]")
            return done
        done += lesson(ctx, book)
        lessons += 1
        if lessons >= ctx.settings["units_per_day"]:
            ui.clear()
            ui.title(f"{ctx.step}Reading")
            console.print(f"{ui.plural(done, 'paragraph')} read. Want to keep going?")
            if ui.keys({"": "finish reading", "y": "one more paragraph"}) != "y":
                return done
