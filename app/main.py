"""Entry point: pick a student, then the daily menu."""
from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import sfx, srs, ui
from .audio import Audio
from .config import load_settings
from .content import Content, load_content, words_in_reach
from .mascot import banner
from .profile import Profile
from .report import print_translation, run_report
from .reading import choose_book, run_reading
from .speaking import speak_and_compare
from .ui import QuitSession, console, icon
from .genders import gender_progress
from .verbs import verb_progress
from .warmup import WarmupResult, run_warmup


@dataclass
class Context:
    settings: dict
    content: Content
    profile: Profile
    audio: Audio
    rng: random.Random
    today: date
    step: str = ""  # e.g. "Today 1/2 · " in front of screen titles during the full lesson


def open_profile(name: str) -> Profile | None:
    try:
        return Profile.open_or_create(name)
    except (OSError, ValueError, AttributeError):
        console.print(f"[warn]The progress file for {ui.escape(name)} is damaged and can't be read. "
                      "Ask a parent to look in data/profiles/.[/]")
        return None


def choose_profile(name: str | None) -> Profile:
    if name:
        profile = open_profile(name)
        if profile is None:
            raise QuitSession
        return profile
    damaged: list = []
    profiles = Profile.list_all(damaged)
    last = Profile.last_used(profiles)
    console.print(banner(width=console.width))
    for path in damaged:
        console.print(f"[warn]Can't read {ui.escape(str(path))} (damaged file), so it's left out.[/]")
    for i, p in enumerate(profiles, 1):
        console.print(f"  [key]{i}[/] {ui.escape(p.name)}" + ("  [hint]← last time[/]" if p is last else ""))
    if last:
        prompt = f"Press Enter to continue as {ui.escape(last.name)}, or pick a number / type a new name:"
    else:
        prompt = "Your number, or type a new name:" if profiles else "Type your name:"
    while True:
        answer = ui.ask(prompt)
        if not answer and last:
            return last
        if answer.isdigit():
            if 1 <= int(answer) <= len(profiles):
                return profiles[int(answer) - 1]
            console.print(f"[warn]There's no number {answer}. " +
                          (f"Pick 1–{len(profiles)} or type a name.[/]" if profiles else "Type your name.[/]"))
        elif answer:
            profile = open_profile(answer)
            if profile:
                return profile
        else:
            console.print("[warn]Type your name to start (or q to quit).[/]")


def warmup_size(ctx: Context) -> int:
    return srs.warmup_size(ctx.settings, ctx.profile.practice_days(ctx.today))


def facts(ctx: Context) -> list[str]:
    states = [s for wid, s in ctx.profile.data["vocab"].items() if wid in ctx.content.words]
    started = sum(1 for s in states if s.get("box", 0) >= 1)
    learned = sum(1 for s in states if s.get("box", 0) >= srs.LEARNED_BOX)
    streak = ctx.profile.streak(ctx.today)
    today = ctx.profile.day(ctx.today)
    lines = [f"{icon('fire')} {ui.plural(streak, 'day')} in a row" if streak else "Start a streak today!",
             f"{started} words started · {learned} learned"]
    if today.get("warmups"):
        lines.append(f"[good]{icon('done')} Warm-up done today[/] (extra practice any time)")
    else:
        lines.append(f"Today's warm-up: {warmup_size(ctx)} words")
    return lines


def welcome(ctx: Context) -> None:
    ui.clear()
    console.print(banner(ctx.profile.name, width=console.width,
                         heading=(f"Willkommen, {ctx.profile.name}!", f"Welcome, {ctx.profile.name}!")))
    console.print(Panel(Text.from_markup(
        "[bold]1.[/] Every day, choose [key]1[/]: a vocabulary warm-up, then a new paragraph of a German book\n"
        "   and a look back at earlier ones. Repetition is how it sticks!\n"
        "   The warm-up starts with 10 words and grows a little every day you practise.\n"
        "[bold]2.[/] The coloured tag at the top of each screen tells you what to do:\n   "
        + " ".join(f"[bold white on {colour}] {kind.upper()} [/]" for kind, colour in ui.TODO.items()) + "\n"
        "   Type your answers. No ä ö ü ß on your keyboard? Type ae oe ue ss.\n"
        f"[bold]3.[/] Sometimes it's a {icon('mic')} speaking turn: you hear yourself next to the right pronunciation.\n"
        "[bold]4.[/] Press [key]q[/] any time to stop. Your progress is always saved."),
        title="How it works", border_style="magenta", padding=(1, 2)))
    if ctx.audio.can_speak and ui.keys({"": "test my speakers & microphone now", "s": "skip"}) == "":
        audio_check(ctx)
    elif not ctx.audio.can_speak:
        ui.keys({"": "let's go"})


def finish_screen(ctx: Context, warm: WarmupResult | None, paragraphs: int | None) -> None:
    ui.clear()
    lines = []
    if warm is not None:
        what = "Extra practice" if warm.extra_practice else "Warm-up"
        lines.append(f"{what}: [good]{warm.correct} correct[/] · [almost]{warm.almost} almost[/] · "
                     f"[bad]{len(warm.to_practise)} to practise[/]")
        if warm.to_practise:
            names = ", ".join(w.de for w in warm.to_practise[:6]) + (" …" if len(warm.to_practise) > 6 else "")
            lines.append(f"[hint]Practise: {ui.escape(names)}[/]")
        if warm.spoken:
            lines.append(f"{icon('mic')} {ui.plural(warm.spoken, 'speaking turn')}")
        for label, drill in (("Verb forms", warm.verbs), ("der / die / das", warm.genders), ("Grammar", warm.grammar)):
            if drill.total:
                lines.append(f"{label}: [good]{drill.right} of {drill.total} right[/]")
    if paragraphs is not None:
        lines.append(f"{icon('book')} {ui.plural(paragraphs, 'new paragraph')} read")
        looked_back = ctx.profile.day(ctx.today).get("reviews", 0)
        if looked_back:
            lines.append(f"{icon('book')} {ui.plural(looked_back, 'paragraph')} looked back at today")
    # This activity's time isn't saved until it ends, so add the clock to what today already has.
    minutes = max(1, round((ctx.profile.day(ctx.today).get("seconds", 0) + ui.clock_seconds()) / 60))
    streak = ctx.profile.streak(ctx.today)
    streak_text = f"{icon('fire')} {ui.plural(streak, 'day')} in a row" if streak else "Finish a warm-up or a paragraph to start a streak"
    lines.append(f"{streak_text} · {ui.plural(minutes, 'minute')} practised today")
    lines.append(f"[hint]Tomorrow's warm-up: {srs.warmup_size(ctx.settings, ctx.profile.practice_days(date.fromordinal(ctx.today.toordinal() + 1)))} words[/]")
    console.print(banner(ctx.profile.name, lines, width=console.width,
                         heading=(f"Gut gemacht, {ctx.profile.name}!", f"Well done, {ctx.profile.name}!")))
    ui.keys({"": "back to the menu"})


def show_progress(ctx: Context) -> None:
    ui.clear()
    states = ctx.profile.data["vocab"]
    words = ctx.content.words
    ui.title(f"Progress: {ctx.profile.name}")
    boxes = [sum(1 for wid, s in states.items() if wid in words and s.get("box", 0) == b) for b in range(6)]
    right = sum(s.get("right", 0) for s in states.values())
    wrong = sum(s.get("wrong", 0) for s in states.values())
    t = Table(show_header=False, box=None, padding=(0, 2))
    reach = words_in_reach(ctx.content, ctx.profile.data)
    t.add_row("Words so far", f"{len(reach):,} [hint](every paragraph you read adds its key words)[/]")
    t.add_row("Not started yet", f"{len(reach) - sum(boxes[1:]):,}")
    t.add_row("Learning", str(boxes[1] + boxes[2]))
    t.add_row("Learned", f"[good]{sum(boxes[3:])}[/]")
    t.add_row("Answers right", f"{right * 100 // (right + wrong)}%" if right + wrong else "–")
    t.add_row("Days in a row", str(ctx.profile.streak(ctx.today)))
    t.add_row("Today's warm-up size", ui.plural(warmup_size(ctx), "word"))
    learned_paragraphs = sum(c.get("paragraphs_learned", 0) for c in ctx.profile.data["days"].values())
    t.add_row("Paragraphs", f"{len(ctx.profile.data['paragraph_reviews'])} being repeated · "
                            f"[good]{learned_paragraphs} learned for good[/]")
    t.add_row("Irregular verbs", verb_progress(ctx.profile.data["verbs"]))
    t.add_row("der / die / das", gender_progress(ctx.profile.data["genders"]))
    console.print(t)

    narrow = console.width < 70
    books = Table(title="Books", title_justify="left")
    for col in ("#", "Title") + (() if narrow else ("Author", "Level")) + ("Paragraphs read",):
        books.add_column(col)
    for i, b in enumerate(ctx.content.books, 1):
        nxt = ctx.profile.book_state(b.id)["next"]
        read = f"{icon('done')} finished" if b.finished(nxt) else f"{b.parts_read(nxt)} of {b.parts}"
        books.add_row(str(i), b.short_title, *(() if narrow else (b.author, b.level)), read)
    console.print(books)

    recent = sorted(ctx.profile.data["days"].items())[-7:]
    untimed = any("seconds" not in v for _, v in recent)
    days = Table(title="Last 7 practice days", title_justify="left", caption_justify="left",
                 caption="– = time not recorded (older app version)" if untimed else None)
    cols = (("Date", "Words", "Right", "Almost", "New", "Para.", "Min.") if narrow else
            ("Date", "Words", "Correct", "Almost", "New", "Paragraphs", "Minutes"))
    for col in cols:
        days.add_column(col, no_wrap=True)
    for d, v in recent:
        seconds = v.get("seconds")
        days.add_row(date.fromisoformat(d).strftime("%d %b" if narrow else "%a %d %b"), str(v.get("words", 0)),
                     str(v.get("right", 0)), str(v.get("almost", 0)), str(v.get("new", 0)), str(v.get("units", 0)),
                     "–" if seconds is None else ("<1" if 0 < seconds < 30 else str(round(seconds / 60))))
    console.print(days)
    ui.keys({"": "back"})


def show_journal(ctx: Context) -> None:
    ui.clear()
    books = {b.id: b for b in ctx.content.books}
    entries = [e for e in ctx.profile.read_journal(30) if e.get("task") != "read_aloud"][-10:]
    ui.title("My translations", "the last 10")
    if not entries:
        console.print("[hint]No translations yet.[/]")
    for e in entries:
        print_translation(e, books)
    console.print()
    ui.keys({"": "back"})


def audio_check(ctx: Context) -> None:
    ui.clear()
    ui.title("Speaker & microphone check")
    for problem in ctx.audio.problems:
        console.print(f"[warn]• {problem}[/]")
    if not ctx.audio.can_speak:
        ui.keys({"": "back"})
        return
    console.print("You should hear: [de]Hallo! Das ist ein Test.[/]")
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
    if ctx.profile.is_new:
        try:
            welcome(ctx)
        except QuitSession:
            pass
    message = ""
    while True:
        ui.clear()
        console.print(banner(ctx.profile.name, facts(ctx), width=console.width))
        for problem in ctx.audio.problems:
            console.print(f"[warn]• {problem}[/]")
        console.print()
        for key, label in MENU.items():
            console.print(f"  [key]{key}[/]  {label}")
        if message:
            console.print(message)
            message = ""
        choice = ui.ask("Choose:").lower()  # q / Ctrl+C here leaves the app
        ctx.today = date.today()  # after the wait: the menu may have been left open overnight
        ui.start_clock()
        ctx.step = ""
        try:
            if choice == "1":
                ctx.step = "Today 1/2 · "
                warm = run_warmup(ctx)
                ctx.step = "Today 2/2 · "
                paragraphs = run_reading(ctx)
                finish_screen(ctx, warm, paragraphs)
            elif choice == "2":
                warm = run_warmup(ctx)
                if warm:
                    finish_screen(ctx, warm, None)
                else:
                    ui.keys({"": "back"})
            elif choice == "3":
                finish_screen(ctx, None, run_reading(ctx))
            elif choice == "4":
                ui.clear()
                message = choose_book(ctx)
            elif choice == "5":
                show_progress(ctx)
            elif choice == "6":
                show_journal(ctx)
            elif choice == "7":
                audio_check(ctx)
            elif choice:
                message = f"[warn]'{ui.escape(choice)}' isn't an option. Pick 1–7, or q to quit.[/]"
        except QuitSession:
            message = "[hint]Stopped. Your progress is saved.[/]"
        finally:
            if choice in ("1", "2", "3"):
                ctx.profile.add_time(ctx.today, ui.clock_seconds())
        ctx.profile.save()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gtutor", description="Offline German tutor")
    parser.add_argument("--profile", help="student name (skips the chooser)")
    parser.add_argument("--no-audio", action="store_true", help="run without speech or microphone")
    parser.add_argument("command", nargs="?", choices=["update", "report"],
                        help="update: download the latest app, words and books; "
                             "report: every kid's progress on one screen (for parents)")
    args = parser.parse_args(argv)
    if args.command == "update":
        from .update import run_update
        return run_update()
    if args.command == "report":
        return run_report(args.profile)

    settings = load_settings()
    content = load_content()
    if content.problems:
        console.print(f"[warn]{len(content.problems)} content problem(s). "
                      "Run tools/validate_content.py for details.[/]")
    profile = None
    unlock = ui.lock_console()
    try:
        profile = choose_profile(args.profile)
        with console.status("Waking up Fritz (loading the German voice)…"):
            audio = Audio(settings, enabled=not args.no_audio)
        ui.BUZZ[0] = lambda: sfx.play(audio, "buzz", wait=False)
        menu(Context(settings, content, profile, audio, random.Random(), date.today()))
    except (KeyboardInterrupt, QuitSession):
        pass
    finally:
        unlock()
        if profile:
            profile.save()
    console.print("\n[bold cyan]Tschüss![/] [green]Bye![/]")
    return 0
