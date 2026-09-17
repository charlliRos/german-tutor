"""`gtutor report`: every kid's practice, words, books and translations on one screen, for the parent.

Only reads the profiles, never changes them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import srs, ui
from .content import Book, Content, load_content
from .profile import Profile
from .ui import console, icon

CALENDAR_WEEKS = 4
HARD_WORDS = 10
TRANSLATIONS = 5
NOT_RECORDED = "time not recorded yet"


def print_translation(entry: dict, books: dict[str, Book], who: str = "You") -> None:
    book = books.get(entry["book"])
    to_english = entry["task"] == "de2en"
    when = datetime.fromisoformat(entry["date"]).strftime("%a %d %b %H:%M")
    grade = "skipped" if entry.get("skipped") else entry.get("self_grade", "")
    console.print(f"\n[bold]{when}[/]  {ui.escape(book.short_title if book else entry['book'])} · "
                  f"paragraph {entry['unit']} · {'German → English' if to_english else 'English → German'} · "
                  f"[note]{grade}[/]")
    # Labels in their own column, so long texts wrap under the text and not under the label.
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column()
    grid.add_row(f"  {ui.escape(who)}:", Text(entry.get("answer") or "(nothing written)", style="magenta"))
    unit = next((u for u in book.units if u.kind == "text" and u.part == entry["unit"]), None) if book else None
    if unit:
        grid.add_row("  Reference:", Text(unit.en if to_english else unit.de))
    console.print(grid)


def _when(day: date | None, today: date, short: bool = False) -> str:
    if day is None:
        return "[warn]never[/]"
    ago = (today - day).days
    if ago == 0:
        return "today"
    if ago == 1:
        return "yesterday"
    return f"{ago} days ago" if short else f"{day.strftime('%a %d %b')} ({ago} days ago)"


def _last_practised(profile: Profile) -> date | None:
    days = [d for d, c in profile.data["days"].items() if Profile.practised(c)]
    return date.fromisoformat(max(days)) if days else None


def _duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def _period(profile: Profile, today: date, length: int) -> tuple[str, str]:
    """(practice days, practice time) for the last `length` days, today included."""
    first = today - timedelta(days=length - 1)
    days = {d: c for d, c in profile.data["days"].items() if d >= first.isoformat()}
    practised = sum(1 for c in days.values() if Profile.practised(c))
    timed = sorted(d for d, c in profile.data["days"].items() if "seconds" in c)
    if not timed:
        time = NOT_RECORDED
    else:
        time = _duration(sum(c.get("seconds", 0) for c in days.values()))
        if timed[0] > first.isoformat():  # recording started inside this period
            time += f" (recorded since {date.fromisoformat(timed[0]).strftime('%d %b')})"
    return f"{practised} of {length} days", time


def _calendar(profile: Profile, today: date) -> Table:
    """The last few weeks, Monday to Sunday, one mark per day."""
    start = today - timedelta(days=today.weekday() + 7 * (CALENDAR_WEEKS - 1))
    weekdays = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
    grid = Table.grid(padding=(0, 1))
    for _ in weekdays:
        grid.add_column(justify="center", no_wrap=True)
    grid.add_row(*(f"[hint]{n}[/]" for n in weekdays))
    for week in range(CALENDAR_WEEKS):
        cells = []
        for weekday in range(7):
            day = start + timedelta(days=7 * week + weekday)
            if day > today:
                cells.append("")
            elif Profile.practised(profile.data["days"].get(day.isoformat(), {})):
                cells.append(f"[good]{icon('day')}[/]")
            else:
                cells.append(f"[hint]{icon('no_day')}[/]")
        grid.add_row(*cells)
    return grid


def _word_counts(profile: Profile, content: Content) -> tuple[int, int, int]:
    """(learning, learned, not started), the same split as the kid's "My progress" screen."""
    boxes = [s.get("box", 0) for wid, s in profile.data["vocab"].items() if wid in content.words]
    learning = sum(1 for b in boxes if 1 <= b < srs.LEARNED_BOX)
    learned = sum(1 for b in boxes if b >= srs.LEARNED_BOX)
    return learning, learned, len(content.words) - learning - learned


def _overview(profiles: list[Profile], content: Content, today: date) -> Table:
    narrow = console.width < 100  # then only the practice columns, so nothing is cut off
    t = Table(title="Overview · last 7 days", title_justify="left")
    t.add_column("Kid", no_wrap=True, max_width=12 if narrow else 16, overflow="ellipsis")
    for col in ("Last practised", "Practised", "Time") + (() if narrow else ("In a row", "Learned")):
        t.add_column(col, no_wrap=True)
    for p in profiles:
        days, time = _period(p, today, 7)
        row = [f"[bold]{ui.escape(p.name)}[/]", _when(_last_practised(p), today, short=narrow), days,
               "–" if time == NOT_RECORDED else time.split(" (")[0]]
        if not narrow:
            row += [ui.plural(p.streak(today), "day"), f"{_word_counts(p, content)[1]} words"]
        t.add_row(*row)
    return t


def _summary(profile: Profile, content: Content, today: date) -> Table:
    states = [s for wid, s in profile.data["vocab"].items() if wid in content.words]
    right = sum(s.get("right", 0) for s in states)
    wrong = sum(s.get("wrong", 0) for s in states)
    learning, learned, not_started = _word_counts(profile, content)

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(no_wrap=True)
    t.add_column()
    t.add_row("Last practised", _when(_last_practised(profile), today))
    for length in (7, 30):
        days, time = _period(profile, today, length)
        t.add_row(f"Last {length} days", f"{days} · {time}")
    t.add_row(f"Last {CALENDAR_WEEKS} weeks", _calendar(profile, today))
    t.add_row("", f"[good]{icon('day')}[/] = finished a warm-up or a paragraph")
    t.add_row("", f"[hint]{icon('no_day')}[/] = no practice")
    t.add_row("Days in a row", str(profile.streak(today)))
    t.add_row("Words", f"{learning} learning · [good]{learned} learned[/] · {not_started:,} not started")
    t.add_row("Answers right", f"{right * 100 // (right + wrong)}%" if right + wrong else "–")

    books = {b.id: b for b in content.books}
    finished = [b for b in content.books if b.id in profile.data["books"] and b.finished(profile.book_state(b.id)["next"])]
    current = books.get(profile.data.get("current_book"))
    if current:
        nxt = profile.book_state(current.id)["next"]
        reading = f"{ui.escape(current.short_title)}: {current.parts_read(nxt)} of {current.parts} paragraphs read"
    else:
        reading = "not started"
    t.add_row("Reading", reading + (f" · {ui.plural(len(finished), 'book')} finished" if finished else ""))
    return t


def _hard_words(profile: Profile, content: Content) -> Table | None:
    """Words still being learned, most missed first (words learned since then are left out)."""
    missed = [(content.words[wid], s) for wid, s in profile.data["vocab"].items()
              if wid in content.words and s.get("wrong", 0) and s.get("box", 0) < srs.LEARNED_BOX]
    if not missed:
        return None
    missed.sort(key=lambda ws: (-ws[1]["wrong"], ws[1].get("right", 0)))
    t = Table(title=f"{ui.escape(profile.name)}'s trickiest words (still learning)", title_justify="left")
    for col in ("German", "English", "Missed", "Right"):
        t.add_column(col)
    for word, s in missed[:HARD_WORDS]:
        t.add_row(Text(word.de, style="de"), Text(", ".join(word.en[:2]), style="en"),
                  str(s["wrong"]), str(s.get("right", 0)))
    return t


def _report(profile: Profile, content: Content, today: date) -> None:
    name = ui.escape(profile.name)
    console.print(Panel(Text(profile.name, style="bold", justify="center"), border_style="magenta"))
    console.print(_summary(profile, content, today))
    console.print()
    hard = _hard_words(profile, content)
    if hard:
        console.print(hard)
    elif any(s.get("seen", 0) for s in profile.data["vocab"].values()):
        console.print(f"[hint]{name} has no tricky words right now.[/]")
    else:
        console.print(f"[hint]{name} hasn't practised any words yet.[/]")

    entries = [e for e in profile.read_journal(None) if e.get("task") != "read_aloud"][-TRANSLATIONS:]
    console.print(f"\n[bold]{name}'s last {TRANSLATIONS} translations[/] "
                  "[hint](the grade is the one they gave themselves)[/]")
    if not entries:
        console.print("[hint]No translations yet.[/]")
    books = {b.id: b for b in content.books}
    for e in entries:
        print_translation(e, books, who=profile.name)
    console.print()


def run_report(name: str | None = None) -> int:
    damaged: list = []
    everyone = sorted(Profile.list_all(damaged), key=lambda p: p.name.casefold())
    for path in damaged:
        console.print(f"[warn]Can't read {ui.escape(str(path))} (damaged file), so it's left out.[/]")
    profiles = [p for p in everyone if p.name.casefold() == name.strip().casefold()] if name else everyone
    if not profiles:
        if not everyone:
            console.print("[warn]No profiles yet.[/]")
        else:
            names = ", ".join(ui.escape(p.name) for p in everyone)
            console.print(f"[warn]No profile called {ui.escape(name or '')}.[/] Profiles: {names}")
        return 1
    content = load_content()
    today = date.today()
    console.print(f"[bold]Progress report[/] · {today.strftime('%a %d %b %Y')}\n")
    console.print(_overview(profiles, content, today))
    console.print()
    for profile in profiles:
        _report(profile, content, today)
    return 0
