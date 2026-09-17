"""`gtutor report`: every kid's practice, words, books and translations on one screen, for the parent.

Only reads the profiles, never changes them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from rich.table import Table
from rich.text import Text

from . import srs, ui
from .content import Book, Content, load_content
from .profile import Profile
from .ui import console, icon

CALENDAR_WEEKS = 4
HARD_WORDS = 10
TRANSLATIONS = 5


def print_translation(entry: dict, books: dict[str, Book], who: str = "You") -> None:
    book = books.get(entry["book"])
    to_english = entry["task"] == "de2en"
    when = datetime.fromisoformat(entry["date"]).strftime("%a %d %b %H:%M")
    grade = "skipped" if entry.get("skipped") else entry.get("self_grade", "")
    console.print(f"\n[bold]{when}[/]  {ui.escape(book.short_title if book else entry['book'])} · "
                  f"part {entry['unit']} · {'German → English' if to_english else 'English → German'} · "
                  f"[note]{grade}[/]")
    console.print(Text(f"  {who + ':':<11}" + (entry.get("answer") or "(nothing written)"), style="magenta"))
    unit = next((u for u in book.units if u.kind == "text" and u.part == entry["unit"]), None) if book else None
    if unit:
        console.print(Text("  Reference: " + (unit.en if to_english else unit.de), style="hint"))


def _practised(counts: dict) -> bool:
    return bool(counts.get("words") or counts.get("units"))


def _when(day: date, today: date) -> str:
    ago = (today - day).days
    if ago == 0:
        return "today"
    if ago == 1:
        return "yesterday"
    return f"{day.strftime('%a %d %b')} ({ago} days ago)"


def _duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def _period(profile: Profile, today: date, length: int) -> str:
    first = (today - timedelta(days=length - 1)).isoformat()
    days = [c for d, c in profile.data["days"].items() if d >= first and _practised(c)]
    text = f"{len(days)} of {length} days"
    if any("seconds" in c for c in days):
        text += f" · {_duration(sum(c.get('seconds', 0) for c in days))}"
    return text


def _calendar(profile: Profile, today: date) -> str:
    """One mark per day for the last few weeks, oldest first, a space between weeks."""
    marks = []
    for i in range(CALENDAR_WEEKS * 7 - 1, -1, -1):
        counts = profile.data["days"].get((today - timedelta(days=i)).isoformat(), {})
        marks.append(f"[good]{icon('day')}[/]" if _practised(counts) else f"[hint]{icon('no_day')}[/]")
        if i and i % 7 == 0:
            marks.append(" ")
    return "".join(marks) + "  [hint]← today[/]"


def _summary(profile: Profile, content: Content, today: date) -> Table:
    words = content.words
    states = {wid: s for wid, s in profile.data["vocab"].items() if wid in words}
    started = sum(1 for s in states.values() if s.get("box", 0) >= 1)
    learned = sum(1 for s in states.values() if s.get("box", 0) >= srs.LEARNED_BOX)
    right = sum(s.get("right", 0) for s in states.values())
    wrong = sum(s.get("wrong", 0) for s in states.values())
    practised = sorted(d for d, c in profile.data["days"].items() if _practised(c))

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("Last practised", _when(date.fromisoformat(practised[-1]), today) if practised else "[warn]never[/]")
    t.add_row("Last 7 days", _period(profile, today, 7))
    t.add_row("Last 30 days", _period(profile, today, 30))
    t.add_row(f"Last {CALENDAR_WEEKS} weeks", _calendar(profile, today))
    t.add_row("Days in a row", str(profile.streak(today)))
    t.add_row("Words", f"{started} started · [good]{learned} learned[/] · {len(words):,} in the bank")
    t.add_row("Right first time", f"{right * 100 // (right + wrong)}%" if right + wrong else "–")

    books = {b.id: b for b in content.books}
    finished = [b for b in content.books if b.id in profile.data["books"] and b.finished(profile.book_state(b.id)["next"])]
    current = books.get(profile.data.get("current_book"))
    if current:
        nxt = profile.book_state(current.id)["next"]
        reading = f"{ui.escape(current.short_title)}: part {current.parts_read(nxt)} of {current.parts}"
    else:
        reading = "not started"
    t.add_row("Reading", reading + (f" · {ui.plural(len(finished), 'book')} finished" if finished else ""))
    return t


def _hard_words(profile: Profile, content: Content) -> Table | None:
    missed = [(content.words[wid], s) for wid, s in profile.data["vocab"].items()
              if wid in content.words and s.get("wrong", 0)]
    if not missed:
        return None
    missed.sort(key=lambda ws: (-ws[1]["wrong"], ws[1].get("right", 0)))
    t = Table(title="Hardest words (most missed)", title_justify="left")
    for col in ("German", "English", "Missed", "Right", "Now"):
        t.add_column(col)
    for word, s in missed[:HARD_WORDS]:
        now = "[good]learned[/]" if s.get("box", 0) >= srs.LEARNED_BOX else "learning"
        t.add_row(Text(word.de, style="de"), Text(", ".join(word.en[:2]), style="en"),
                  str(s["wrong"]), str(s.get("right", 0)), now)
    return t


def _report(profile: Profile, content: Content, today: date) -> None:
    ui.title(profile.name)
    console.print(_summary(profile, content, today))
    tracked = sorted(d for d, c in profile.data["days"].items() if "seconds" in c)
    if not tracked or tracked[0] > (today - timedelta(days=29)).isoformat():
        since = date.fromisoformat(tracked[0]).strftime("%d %b %Y") if tracked else "the next lesson"
        console.print(f"[hint]Practice time is only recorded from {since} on.[/]")
    console.print()
    hard = _hard_words(profile, content)
    console.print(hard if hard else "[hint]No missed words yet.[/]")

    entries = [e for e in profile.read_journal(None) if e.get("task") != "read_aloud"][-TRANSLATIONS:]
    console.print(f"\n[bold]Last {TRANSLATIONS} translations[/] [hint](the grade is the one they gave themselves)[/]")
    if not entries:
        console.print("[hint]No translations yet.[/]")
    books = {b.id: b for b in content.books}
    for e in entries:
        print_translation(e, books, who=profile.name)
    console.print()


def run_report(name: str | None = None) -> int:
    profiles = Profile.list_all()
    if name:
        profiles = [p for p in profiles if p.name.casefold() == name.strip().casefold()]
    if not profiles:
        console.print(f"[warn]No profile called {ui.escape(name)}.[/]" if name else "[warn]No profiles yet.[/]")
        return 1
    content = load_content()
    today = date.today()
    for profile in sorted(profiles, key=lambda p: p.name.casefold()):
        _report(profile, content, today)
    return 0
