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
# Output sent to a file or `more` on Windows uses an old code page: show "?" for symbols it lacks instead of crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
console = Console(highlight=False, theme=THEME)

QUIT_WORDS = {"q", ":q", ":quit", ":exit"}
QUIT_HINT = "[hint](q = stop)[/]"

# Emoji and symbols only where the terminal can show them (Windows Terminal, VS Code, most Linux/macOS terminals).
FANCY = bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")) or (
    os.name != "nt" and os.environ.get("TERM", "") not in ("linux", "dumb", ""))
_ICONS = {"fire": ("🔥", "*"), "mic": ("🎤", "(mic)"), "ok": ("✔", "OK"), "almost": ("≈", "~"),
          "bad": ("✘", "X"), "play": ("▶", ">"), "rec": ("●", "(rec)"), "party": ("🎉", "!"),
          "book": ("📖", "*"), "done": ("✓", "done"), "day": ("■", "#"), "no_day": ("·", "."),
          "current": ("◀", "<")}


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


# Held-down Enter: Windows repeats the key about 30 times a second, which used to answer and skip
# several questions at once. Every prompt first waits until Enter is let go, then ignores keys for a
# moment after the last one, so one press = one step.
# Seconds. Windows sees a held key directly, so the mute only has to catch a quick double press;
# elsewhere it must outlast the delay before a held key starts repeating (about half a second).
MUTE_AFTER_KEY = 0.25 if os.name == "nt" else 0.7
REPEAT_GAP = 0.15  # keys closer together than this are a held or mashed key
_last_key = [0.0]  # when the last key reached us (read or thrown away)


def _enter_held() -> bool:
    """True while the Enter key is physically down (Windows only; elsewhere the timing does the job)."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x0D) & 0x8000)
    except Exception:
        return False


def typing_waiting() -> bool:
    """Windows: True if the next waiting key is a letter (the kid has started typing an answer), not Enter.
    It only looks, so the prompt still gets every key. Elsewhere keys only arrive with Enter: False."""
    if os.name != "nt" or not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class KeyEvent(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vkey", wintypes.WORD),
                        ("scan", wintypes.WORD), ("char", wintypes.WCHAR), ("state", wintypes.DWORD)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("type", wintypes.WORD), ("key", KeyEvent)]

        kernel32 = ctypes.windll.kernel32
        records, count = (InputRecord * 64)(), wintypes.DWORD()
        if not kernel32.PeekConsoleInputW(kernel32.GetStdHandle(-10), records, 64, ctypes.byref(count)):
            return False
        chars = [r.key.char for r in records[: count.value] if r.type == 1 and r.key.down and r.key.char != "\x00"]
        return bool(chars) and chars[0] not in "\r\n"
    except Exception:
        return False


def drop_enters() -> None:
    """After audio: throw away Enter presses, but keep an answer the kid has already started typing."""
    if not typing_waiting():
        flush_input()


BUZZ = [None]  # main.py sets this to the "not so fast" sound effect


class _Drain:
    """Throws away keys pressed too early. Buzzes once if Enter is held down or mashed;
    one early press is ignored quietly."""

    def __init__(self) -> None:
        self.buzzed = False
        self.held_since: float | None = None
        self.last_typed = 0.0
        self.typing = False  # the kid started typing an answer: leave the keys for the prompt

    def keys_waiting(self) -> bool:
        """True if keys were waiting (now thrown away) or Enter is still held down."""
        now = time.monotonic()
        typed, held = key_pressed(), _enter_held()
        if typed and typing_waiting():
            self.typing = True
            return False
        self.held_since = (self.held_since or now) if held else None
        held_long = held and now - self.held_since > 0.1  # a new press shows as "held" just before its key arrives
        if typed:
            flush_input()
            repeating = now - max(self.last_typed, _last_key[0]) < REPEAT_GAP
            self.last_typed = now
            if (repeating or held_long) and not self.buzzed and BUZZ[0]:
                self.buzzed = True
                BUZZ[0]()
        if typed or held_long:
            _last_key[0] = now
        return typed or held


def settle() -> None:
    """Before a prompt: drop keys pressed too early, and wait until a held-down Enter is let go."""
    if not console.is_terminal or not sys.stdin or not sys.stdin.isatty():
        return
    drain = _Drain()
    try:
        while True:
            waiting = drain.keys_waiting()
            if drain.typing or (not waiting and time.monotonic() - _last_key[0] >= MUTE_AFTER_KEY):
                return
            time.sleep(0.02)
    except KeyboardInterrupt:
        console.print()
        raise QuitSession from None


def pause(seconds: float, skippable: bool = False) -> None:
    """A moment to read the screen. With skippable, a fresh Enter press goes on straight away.
    Ctrl+C here stops the activity like q (not the whole app)."""
    if not console.is_terminal:
        return
    end = time.monotonic() + seconds
    drain = _Drain()
    try:
        while (now := time.monotonic()) < end:
            # A fresh press: quiet long enough before it, and not a key that's been held down all along.
            held_all_along = drain.held_since is not None and now - drain.held_since > 0.1
            if skippable and key_pressed() and now - _last_key[0] >= MUTE_AFTER_KEY and not held_all_along:
                drop_enters()
                _last_key[0] = now
                return
            drain.keys_waiting()
            time.sleep(0.02)
    except KeyboardInterrupt:
        console.print()
        raise QuitSession from None


def _read(prompt: str, wait_for_quiet: bool = True) -> str:
    if wait_for_quiet:
        settle()
    try:
        return console.input(f"[bold]{prompt}[/] " if prompt else "")
    except (EOFError, KeyboardInterrupt):
        console.print()
        raise QuitSession from None
    finally:
        _last_key[0] = time.monotonic()
        _tick()


def ask(prompt: str, wait_for_quiet: bool = True) -> str:
    value = _read(prompt, wait_for_quiet).strip()
    if value.lower() in QUIT_WORDS:
        raise QuitSession
    return value


DONT_KNOW = "?"


def ask_answer(prompt: str) -> str:
    """An answer to a question. Enter on its own does nothing (so a held Enter can't skip the question);
    '?' means "I don't know" and returns ''."""
    while True:
        value = ask(prompt)
        if value == DONT_KNOW:
            return ""
        if value:
            return value
        console.print(f"[hint]Type your answer first, or {DONT_KNOW} if you don't know.[/]")


def ask_multiline(prompt: str) -> str:
    """Several lines of text. A single empty line is kept (pasted paragraphs); two in a row finish.
    Empty lines before any text are ignored; '?' as the first line means "I don't know" and returns ''."""
    console.print(f"[bold]{prompt}[/] [hint](press Enter twice when you're done; {DONT_KNOW} if you don't know)[/]")
    first = ask_answer(">")
    if not first:
        return ""
    lines = [first]
    empty_in_a_row = 0
    while True:
        line = ask("…", wait_for_quiet=False)  # no pause between lines, so pasting works
        if line:
            lines.append(line)
            empty_in_a_row = 0
            continue
        empty_in_a_row += 1
        if empty_in_a_row >= 2:
            break
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
