"""Entry point: pick a student, then the daily menu."""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date

from rich.table import Table

from . import srs, ui
from .audio import Audio
from .config import load_settings
from .content import Content, load_content
from .mascot import banner
from .profile import Profile
from .reading import run_reading
from .speaking import speak_and_compare
from .ui import QuitSession, console
from .warmup import run_warmup


@dataclass
class Context:
    settings: dict
    content: Content
    profile: Profile
    audio: Audio
    rng: random.Random
    today: date


def choose_profile(name: str | None) -> Profile:
    if name:
        return Profile.open_or_create(name)
    profiles = Profile.list_all()
    last = Profile.last_used(profiles)
    console.print(banner())
    for i, p in enumerate(profiles, 1):
        console.print(f"  [cyan]{i}[/] {p.name}" + ("  [dim]← last time[/]" if p is last else ""))
    if last:
        prompt = f"Press Enter to continue as {last.name}, or pick a number / type a new name:"
    else:
        prompt = "Your number, or type a new name:" if profiles else "Type your name:"
    while True:
        answer = ui.ask(prompt)
        if not answer and last:
            return last
        if answer.isdigit() and 1 <= int(answer) <= len(profiles):
            return profiles[int(answer) - 1]
        if answer and not answer.isdigit():
            return Profile.open_or_create(answer)


def facts(ctx: Context) -> list[str]:
    states = ctx.profile.data["vocab"]
    learned = sum(1 for s in states.values() if s.get("box", 0) >= srs.LEARNED_BOX)
    due = len(srs.plan_session(states, ctx.content.words, {**ctx.settings, "warmup_words": 10**6}, ctx.today)[0])
    streak = ctx.profile.streak(ctx.today)
    return [f"🔥 {streak}-day streak" if streak else "Start a streak today!",
            f"{learned} words learned · {due} due for review"]


def show_progress(ctx: Context) -> None:
    states = ctx.profile.data["vocab"]
    words = ctx.content.words
    ui.title(f"Progress: {ctx.profile.name}")
    boxes = [sum(1 for wid, s in states.items() if wid in words and s.get("box", 0) == b) for b in range(6)]
    right = sum(s.get("right", 0) for s in states.values())
    wrong = sum(s.get("wrong", 0) for s in states.values())
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("Words in the bank", str(len(words)))
    t.add_row("Not started yet", str(len(words) - sum(boxes[1:])))
    t.add_row("Still learning (box 1–2)", str(boxes[1] + boxes[2]))
    t.add_row("Learned (box 3–5)", f"[green]{sum(boxes[3:])}[/]")
    t.add_row("Accuracy", f"{right * 100 // (right + wrong)}%" if right + wrong else "–")
    t.add_row("Streak", f"{ctx.profile.streak(ctx.today)} day(s)")
    console.print(t)

    books = Table(title="Books", title_justify="left")
    for col in ("#", "Title", "Author", "Level", "Read"):
        books.add_column(col)
    for i, b in enumerate(ctx.content.books, 1):
        read = b.parts_read(ctx.profile.book_state(b.id)["next"])
        books.add_row(str(i), b.title, b.author, b.level, f"{read}/{b.parts}")
    console.print(books)

    days = Table(title="Last 7 practice days", title_justify="left")
    for col in ("Date", "Words", "Correct", "New", "Paragraphs"):
        days.add_column(col)
    for d, v in sorted(ctx.profile.data["days"].items())[-7:]:
        days.add_row(d, str(v.get("words", 0)), str(v.get("right", 0)), str(v.get("new", 0)), str(v.get("units", 0)))
    console.print(days)
    ui.keys({"": "back"})


def choose_book(ctx: Context) -> None:
    table = Table()
    for col in ("#", "Title", "Author", "Year", "Level", "Read"):
        table.add_column(col)
    for i, b in enumerate(ctx.content.books, 1):
        read = b.parts_read(ctx.profile.book_state(b.id)["next"])
        mark = " ◀" if b.id == ctx.profile.data["current_book"] else ""
        table.add_row(str(i), b.title + mark, b.author, str(b.year), b.level, f"{read}/{b.parts}")
    console.print(table)
    answer = ui.ask("Book number (Enter to keep the current one):")
    if answer.isdigit() and 1 <= int(answer) <= len(ctx.content.books):
        ctx.profile.data["current_book"] = ctx.content.books[int(answer) - 1].id
        ctx.profile.save()
        console.print(f"[green]Now reading: {ctx.content.books[int(answer) - 1].title}[/]")


def show_journal(ctx: Context) -> None:
    titles = {b.id: b.title for b in ctx.content.books}
    entries = [e for e in ctx.profile.read_journal(20) if e.get("task") != "read_aloud"]
    ui.title("My translations", "saved in " + str(ctx.profile.journal_path.name))
    if not entries:
        console.print("[dim]No translations yet.[/]")
    for e in entries[-10:]:
        direction = "German → English" if e["task"] == "de2en" else "English → German"
        console.print(f"[bold]{e['date']}[/]  {titles.get(e['book'], e['book'])} · part {e['unit']} · "
                      f"{direction} · [yellow]{e.get('self_grade', '')}[/]")
        console.print(f"  [magenta]{ui.escape(e.get('answer') or '(nothing written)')}[/]")
    ui.keys({"": "back"})


def audio_check(ctx: Context) -> None:
    ui.title("Speaker & microphone check")
    for problem in ctx.audio.problems:
        console.print(f"[yellow]• {problem}[/]")
    if not ctx.audio.can_speak:
        return
    console.print("You should hear: [cyan]Hallo! Das ist ein Test.[/]")
    speak_and_compare(ctx, "Hallo! Das ist ein Test.")


MENU = {
    "1": "Today's lesson (warm-up + reading)",
    "2": "Vocabulary warm-up only",
    "3": "Reading only",
    "4": "Choose a book",
    "5": "My progress",
    "6": "My translations",
    "7": "Test speakers & microphone",
    "q": "Quit",
}


def menu(ctx: Context) -> None:
    ui.clear()
    console.print(banner(ctx.profile.name, facts(ctx)))
    for problem in ctx.audio.problems:
        console.print(f"[yellow]• {problem}[/]")
    while True:
        console.print()
        for key, label in MENU.items():
            console.print(f"  [cyan]{key}[/]  {label}")
        choice = ui.ask("Choose:").lower()
        ctx.today = date.today()
        try:
            if choice == "1":
                run_warmup(ctx)
                ui.keys({"": "on to reading"})
                run_reading(ctx)
            elif choice == "2":
                run_warmup(ctx)
            elif choice == "3":
                run_reading(ctx)
            elif choice == "4":
                choose_book(ctx)
            elif choice == "5":
                show_progress(ctx)
            elif choice == "6":
                show_journal(ctx)
            elif choice == "7":
                audio_check(ctx)
            elif choice == "q":
                console.print("[bold cyan]Tschüss![/] [green]Bye![/]")
                return
        except QuitSession:
            console.print("[dim]Stopped. Your progress is saved.[/]")
        ctx.profile.save()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gtutor", description="Offline German tutor")
    parser.add_argument("--profile", help="student name (skips the chooser)")
    parser.add_argument("--no-audio", action="store_true", help="run without speech or microphone")
    args = parser.parse_args(argv)

    settings = load_settings()
    content = load_content()
    if content.problems:
        console.print(f"[yellow]{len(content.problems)} content problem(s). "
                      "Run tools/validate_content.py for details.[/]")
    profile = None
    try:
        profile = choose_profile(args.profile)
        with console.status("Waking up Fritz (loading the German voice)…"):
            audio = Audio(settings, enabled=not args.no_audio)
        menu(Context(settings, content, profile, audio, random.Random(), date.today()))
    except (KeyboardInterrupt, QuitSession):
        console.print("\n[bold cyan]Tschüss![/]")
    finally:
        if profile:
            profile.save()
    return 0
