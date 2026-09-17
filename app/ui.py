"""Small terminal helpers on top of rich: theme, prompts, key choices, layout."""
from __future__ import annotations

import os
import sys
import time

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Named styles that stay readable on dark AND light terminal backgrounds (no yellow, no dim).
THEME = Theme({
    "de": "cyan",
    "de.word": "bold cyan",
    "en": "green",
    "note": "magenta",
    "hint": "grey50",
    "key": "bold blue",
    "good": "bold green",
    "almost": "bold dark_orange",
    "bad": "bold red",
    "rec": "bold red",
    "warn": "dark_orange",
})
console = Console(highlight=False, theme=THEME)

QUIT_WORDS = {"q", ":q", ":quit", ":exit"}
QUIT_HINT = "[hint](q = stop)[/]"

# Emoji and symbols only where the terminal can show them (Windows Terminal, VS Code, most Linux/macOS terminals).
FANCY = bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")) or (
    os.name != "nt" and os.environ.get("TERM", "") not in ("linux", "dumb", ""))
_ICONS = {"fire": ("🔥", "*"), "mic": ("🎤", "(mic)"), "ok": ("✔", "OK"), "almost": ("≈", "~"),
          "bad": ("✘", "X"), "play": ("▶", ">"), "rec": ("●", "(rec)"), "party": ("🎉", "!"),
          "book": ("📖", "*"), "done": ("✓", "done"), "day": ("■", "#"), "no_day": ("·", ".")}


def icon(name: str) -> str:
    fancy, plain = _ICONS[name]
    return fancy if FANCY else plain


def umlaut_tip() -> str:
    return "[hint]No ä ö ü ß on your keyboard? Type ae oe ue ss.[/]"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


class QuitSession(Exception):
    """The user typed q (or pressed Ctrl+C / closed input) to leave the current activity."""


def clear() -> None:
    """Clear the screen AND the scroll-back, so earlier answers can't be scrolled up to."""
    console.clear()
    if console.is_terminal:
        console.file.write("\x1b[3J")
        console.file.flush()


def flush_input() -> None:
    """Throw away keys pressed while audio was playing, so an impatient Enter doesn't skip the next step."""
    if not sys.stdin or not sys.stdin.isatty():
        return
    try:
        if os.name == "nt":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def key_pressed() -> bool:
    """True if a key (Enter on Linux/macOS) is waiting; used to skip audio."""
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        if os.name == "nt":
            import msvcrt
            return msvcrt.kbhit()
        import select
        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False


# Practice time: the time between answers, with one long pause counted as at most IDLE_LIMIT
# (so walking away from the screen doesn't add an hour).
IDLE_LIMIT = 5 * 60
_clock = {"since": time.monotonic(), "seconds": 0.0}


def start_clock() -> None:
    _clock.update(since=time.monotonic(), seconds=0.0)


def _tick() -> None:
    now = time.monotonic()
    _clock["seconds"] += min(now - _clock["since"], IDLE_LIMIT)
    _clock["since"] = now


def clock_seconds() -> int:
    """Active seconds since start_clock()."""
    _tick()
    return round(_clock["seconds"])


def _read(prompt: str) -> str:
    try:
        return console.input(f"[bold]{prompt}[/] " if prompt else "")
    except (EOFError, KeyboardInterrupt):
        console.print()
        raise QuitSession from None
    finally:
        _tick()


def ask(prompt: str) -> str:
    value = _read(prompt).strip()
    if value.lower() in QUIT_WORDS:
        raise QuitSession
    return value


def ask_multiline(prompt: str) -> str:
    """Several lines of text. A single empty line is kept (pasted paragraphs); two in a row finish."""
    console.print(f"[bold]{prompt}[/] [hint](press Enter twice when you're done)[/]")
    lines: list[str] = []
    empty_in_a_row = 0
    while True:
        line = ask("…" if lines else ">")
        if line:
            lines.append(line)
            empty_in_a_row = 0
            continue
        empty_in_a_row += 1
        if empty_in_a_row >= 2:
            break
    flush_input()
    return "\n".join(lines).strip()


def keys(options: dict[str, str]) -> str:
    """Show e.g. '[Enter] next  [r] hear again' and return the chosen key ('' is Enter)."""
    hint = "   ".join(f"[key]{escape('[' + ('Enter' if k == '' else k) + ']')}[/] {label}"
                      for k, label in options.items())
    if "q" not in options:
        hint += "   " + QUIT_HINT
    while True:
        console.print(hint)
        raw = _read(">").strip().lower()
        if raw in options:
            return raw
        if raw in QUIT_WORDS:
            raise QuitSession
        console.print(f"[warn]'{escape(raw)}' isn't an option here.[/]" if raw else "[warn]Pick one of the options above.[/]")


def title(heading: str, sub: str = "") -> None:
    """A rule line; the subtitle is dropped rather than letting the heading get cut off."""
    room = console.width - 8
    if len(heading) + len(sub) + 2 > room:
        sub = ""
    if len(heading) > room:
        heading = heading[: room - 1] + "…"
    console.rule(f"[bold]{escape(heading)}[/]" + (f"  [hint]{escape(sub)}[/]" if sub else ""))


def german(text: str, heading: str = "Deutsch", subtitle: str | None = None, word: bool = False) -> Panel:
    return Panel(Text(text, style="de.word" if word else "de"), title=heading, subtitle=subtitle,
                 border_style="cyan", padding=(1, 2))


def english(text: str, heading: str = "English") -> Panel:
    return Panel(Text(text, style="en"), title=heading, border_style="green", padding=(1, 2))


def side_by_side(left_title: str, left: str, right_title: str, right: str) -> None:
    left = left or "(nothing written)"
    if console.width < 80:
        console.print(Panel(Text(left), title=left_title, border_style="magenta"))
        console.print(Panel(Text(right, style="de"), title=right_title, border_style="cyan"))
        return
    table = Table(box=box.ROUNDED, expand=True, show_lines=False, padding=(1, 2))
    table.add_column(left_title, ratio=1)
    table.add_column(right_title, ratio=1)
    table.add_row(Text(left, style="magenta"), Text(right, style="cyan"))
    console.print(table)


def key_words(words: list[dict]) -> Table | Text:
    """Key-word list: a table on wide screens, simple 'de – en (note)' lines on narrow ones."""
    if console.width < 70:
        out = Text("Key words\n", style="bold")
        for w in words:
            out.append(w.get("de", ""), style="de.word")
            out.append(f" – {w.get('en', '')}", style="en")
            if w.get("note"):
                out.append(f" ({w['note']})", style="note")
            out.append("\n")
        return out
    table = Table(title="Key words", title_justify="left", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="de.word", no_wrap=True)
    table.add_column(style="en")
    table.add_column(style="note")
    for w in words:
        table.add_row(w.get("de", ""), w.get("en", ""), w.get("note", ""))
    return table
