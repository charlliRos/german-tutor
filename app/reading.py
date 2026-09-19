"""Daily reading: the next paragraph of a classic in 3 rounds, then a look back at earlier paragraphs.

Learning is repetition. A new paragraph is translated, read out loud and translated back. After it,
each session looks back at earlier paragraphs: every paragraph comes back in each of the next
REVIEW_SESSIONS sessions (session 3 repeats sessions 1 and 2) AND on REVIEW_DAYS after it was learned.
A look back marked "needs work" (or skipped) doesn't count, so it comes back next session.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import ui
from .content import Book, Unit
from .speaking import hear, speak_and_compare
from .ui import console, icon

SELF_GRADES = {"1": "needs work", "2": "mostly right", "3": "nailed it"}
NEEDS_WORK = SELF_GRADES["1"]
REVIEW_SESSIONS = 2
REVIEW_DAYS = (1, 3, 7, 16, 35)  # the same ladder as the words


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
        elif book.parts_read(state["next"]):
            console.print(f"You've read {book.parts_read(state['next'])} of {book.parts} paragraphs "
                          f"of {book.short_title}.")
            if ui.keys({"": "carry on where I stopped", "s": "start again from the beginning"}) == "s":
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


def _translate(ctx, book: Book, unit: Unit, direction: str, heading: str, review: bool = False) -> dict:
    """One translation. The journal gets it as soon as it's typed, even if they stop at the self-grade."""
    to_english = direction == "de2en"
    reference = unit.en if to_english else unit.de
    entry = {"date": datetime.now().isoformat(timespec="minutes"), "book": book.id, "unit": unit.part,
             "task": direction, **({"review": True} if review else {})}
    ui.clear()
    ui.title(f"{ctx.step}{heading}: translate into {'English' if to_english else 'German'}", book.short_title)
    if to_english:
        console.print(ui.german(unit.de, "German"))
    else:
        console.print(ui.english(unit.en, "English"))
        if unit.words:
            console.print(ui.key_words(unit.words))
        console.print(ui.umlaut_tip())
    answer = ui.ask_multiline(f"Your {'English' if to_english else 'German'} translation:")
    if not answer:  # typed ? : show the answer, the round counts as skipped
        entry.update(answer="", skipped=True)
        ctx.profile.add_journal(entry)
        console.print(Panel(Text(reference, style="en" if to_english else "de"),
                            title="Reference translation" if to_english else "Original German",
                            border_style="green" if to_english else "cyan", padding=(1, 2)))
        if not to_english:
            hear(ctx, unit.de, slow=False)
        ui.keys({"": "continue"})
        return entry
    entry.update(answer=answer, self_grade="not graded")
    try:
        ui.side_by_side("Your translation", answer,
                        "Reference translation" if to_english else "Original German", reference)
        if not to_english:
            hear(ctx, unit.de, slow=False)
        entry["self_grade"] = _self_grade(ctx, None if to_english else unit.de)
    finally:
        ctx.profile.add_journal(entry)
    return entry


def _read_aloud(ctx, book: Book, unit: Unit, heading: str) -> None:
    ui.clear()
    ui.title(f"{ctx.step}{heading}: read it out loud", book.short_title)
    console.print(ui.german(unit.de))
    if ctx.audio.can_speak:
        speak_and_compare(ctx, unit.de, long_text=True)
    else:
        console.print("Read it out loud to yourself, slowly and clearly.")
        ui.keys({"": "done"})


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


def lesson(ctx, book: Book) -> bool:
    """One new paragraph in 3 rounds: translate it, read it out loud, translate it back.
    Returns True if it counts as read. Stopping halfway keeps the typed translations (journal),
    and the paragraph starts again next time."""
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

    header = f"{ctx.step}Paragraph {unit.part} of {book.total_parts} · {book.short_title}"
    ui.clear()
    ui.title(header, book.author)
    console.print(ui.german(unit.de))
    console.print("[hint]New paragraph: listen and read along. Then 3 rounds: translate it, "
                  "read it out loud, translate it back.[/]")
    hear(ctx, unit.de, slow=False)
    _replay_until_enter(ctx, unit.de, "round 1: translate it")

    # Round 1: try to understand it before seeing the meaning.
    first = _translate(ctx, book, unit, "de2en", "Round 1 of 3")
    ui.clear()
    ui.title(header, "what it means")
    console.print(ui.german(unit.de))
    _explain(unit)
    _replay_until_enter(ctx, unit.de, "round 2: read it out loud")
    # Round 2: say it.
    _read_aloud(ctx, book, unit, "Round 2 of 3")
    # Round 3: build it again from the English.
    last = _translate(ctx, book, unit, "en2de", "Round 3 of 3")

    counted = not (first.get("skipped") and last.get("skipped"))
    state["next"] = unit.n + 1
    ctx.profile.data["current_book"] = book.id
    if counted:
        ctx.profile.count(ctx.today, units=1)
    _schedule_reviews(ctx, book, unit)
    ctx.profile.save()
    if book.finished(state["next"]):
        _story_so_far(ctx, book, state)  # a closing summary, if the book ends with one
        _celebrate(ctx, book)
    return counted


def _schedule_reviews(ctx, book: Book, unit: Unit) -> None:
    """The paragraph comes back in the next sessions, and its key words join the warm-up."""
    ctx.profile.data["paragraph_reviews"][f"{book.id}:{unit.n}"] = {
        "book": book.id, "n": unit.n, "learned": ctx.today.isoformat(), "sessions_left": REVIEW_SESSIONS,
        "due_days": [(ctx.today + timedelta(days=d)).isoformat() for d in REVIEW_DAYS], "last_task": "en2de"}
    queue = ctx.profile.data["reading_words"]
    queue.extend(wid for wid in unit.word_ids if wid not in queue)


def due_reviews(ctx) -> list[tuple[Book, Unit, dict]]:
    """Paragraphs to look back at, oldest first: from the last sessions, or with a review day that has come."""
    books = {b.id: b for b in ctx.content.books}
    out = []
    for key, item in list(ctx.profile.data["paragraph_reviews"].items()):
        book = books.get(item["book"])
        unit = next((u for u in book.units if u.n == item["n"] and u.kind == "text"), None) if book else None
        if unit is None:  # the text was changed or removed
            del ctx.profile.data["paragraph_reviews"][key]
            continue
        if item["sessions_left"] > 0 or (item["due_days"] and item["due_days"][0] <= ctx.today.isoformat()):
            out.append((book, unit, item))
    out.sort(key=lambda r: r[2]["learned"])  # stable: same day keeps reading order
    return out[: max(0, int(ctx.settings["paragraph_reviews_per_session"]))]


def _review_task(ctx, last: str) -> str:
    """A different exercise from last time, so each look back practises something else."""
    tasks = [t for t in ("read_aloud", "de2en", "en2de") if ctx.settings["reading_tasks"].get(t, 0) > 0]
    tasks = [t for t in tasks if t != last] or tasks or ["de2en"]
    return ctx.rng.choice(tasks)


def review(ctx, book: Book, unit: Unit, item: dict, i: int, total: int) -> None:
    task = _review_task(ctx, item.get("last_task", ""))
    heading = f"Look back {i} of {total} · paragraph {unit.part}"
    if task == "read_aloud":
        _read_aloud(ctx, book, unit, heading)
        ok = True
    else:
        entry = _translate(ctx, book, unit, task, heading, review=True)
        ok = not entry.get("skipped") and entry.get("self_grade") != NEEDS_WORK
    item["last_task"] = task
    if ok:  # one good look back counts for this session and every review day that has come
        item["sessions_left"] = max(0, item["sessions_left"] - 1)
        item["due_days"] = [d for d in item["due_days"] if d > ctx.today.isoformat()]
        if not item["sessions_left"] and not item["due_days"]:
            del ctx.profile.data["paragraph_reviews"][f"{book.id}:{unit.n}"]  # learned for good
    ctx.profile.count(ctx.today, reviews=1)
    ctx.profile.save()


def look_back(ctx, reviews: list[tuple[Book, Unit, dict]]) -> None:
    if not reviews:
        return
    ui.clear()
    ui.title(f"{ctx.step}Look back")
    console.print(f"Now {ui.plural(len(reviews), 'paragraph')} you read before. Repetition is how it sticks!")
    ui.keys({"": "start"})
    for i, (book, unit, item) in enumerate(reviews, 1):
        review(ctx, book, unit, item, i, len(reviews))


def run_reading(ctx) -> int:
    """New paragraphs until the daily amount is reached (and more if wanted), then a look back at the
    paragraphs of earlier sessions. Returns new paragraphs read."""
    reviews = due_reviews(ctx)  # chosen now: today's new paragraph waits for the next sessions
    done = lessons = 0
    while True:
        book = current_book(ctx)
        if book is None:
            console.print("[good]You've read every paragraph we have! Ask for new texts.[/]")
            break
        done += lesson(ctx, book)
        lessons += 1
        if lessons >= ctx.settings["units_per_day"]:
            ui.clear()
            ui.title(f"{ctx.step}Reading")
            console.print(f"{ui.plural(done, 'paragraph')} read."
                          + (" Then a look back at earlier ones." if reviews else "") + " Want another new one first?")
            if ui.keys({"": "go on" if reviews else "finish reading", "y": "one more paragraph"}) != "y":
                break
    look_back(ctx, reviews)
    return done
