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
          "current": ("◀", "<"), "news": ("📣", ">>")}


def icon(name: str) -> str:
    fancy, plain = _ICONS[name]
    return fancy if FANCY else plain


def umlaut_tip() -> str:
    return "[hint]No ä ö ü ß on your keyboard? Type ae oe ue ss.[/]"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


class QuitSession(Exception):
    """The user typed q (or pressed Ctrl+C / closed input) to leave the current activity."""


NEWS = [None]  # main.py sets this: news from the others on the Wi-Fi, shown at the top of the next screen


def clear() -> None:
    """Clear the screen AND the scroll-back, so earlier answers can't be scrolled up to.
    News from the others on the Wi-Fi ("Anna just finished a warm-up") goes at the top: between
    screens, never in the middle of a question."""
    console.clear()
    if console.is_terminal:
        console.file.write("\x1b[3J")
        console.file.flush()
    for line in NEWS[0]() if NEWS[0] else []:
        console.print(f"[bold magenta]{icon('news')} {escape(line)}[/]")


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


_RECORD = []


def _input_record():
    """The Windows console INPUT_RECORD (only its key-event part), made once."""
    if not _RECORD:
        import ctypes
        from ctypes import wintypes

        class KeyEvent(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vkey", wintypes.WORD),
                        ("scan", wintypes.WORD), ("char", wintypes.WCHAR), ("state", wintypes.DWORD)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("type", wintypes.WORD), ("key", KeyEvent)]

        _RECORD.append(InputRecord)
    return _RECORD[0]


def lock_console():
    """Windows' classic console: switch off selecting and right-click pasting with the mouse (QuickEdit).
    Returns a function that switches it back. Windows Terminal ignores this: there, pasting is caught
    by the answer prompts (see PASTE_BURST)."""
    if os.name != "nt" or not sys.stdin or not sys.stdin.isatty():
        return lambda: None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        hin, mode = kernel32.GetStdHandle(-10), wintypes.DWORD()
        if not kernel32.GetConsoleMode(hin, ctypes.byref(mode)):
            return lambda: None
        old = mode.value
        kernel32.SetConsoleMode(hin, (old | 0x0080) & ~0x0040)  # extended flags on, QuickEdit off
        return lambda: kernel32.SetConsoleMode(hin, old)
    except Exception:
        return lambda: None


def typing_waiting() -> bool:
    """Windows: True if the next waiting key is a letter (the kid has started typing an answer), not Enter.
    It only looks, so the prompt still gets every key. Elsewhere keys only arrive with Enter: False."""
    if os.name != "nt" or not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        records, count = (_input_record() * 64)(), wintypes.DWORD()
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


# No pasting: a terminal can't switch paste off, but pasted text arrives all at once and typing doesn't,
# so answers are read key by key and a burst of keys is thrown away.
PASTE_BURST = 10    # keys arriving together: more than anyone can type at once
PASTE_QUIET = 0.3   # seconds without keys that end a paste (a long one arrives in pieces)
PASTE_START = 0.15  # keys typed this shortly before a paste belong to it
_pastes = [0]       # paste attempts so far (callers compare before and after a question)


def paste_count() -> int:
    return _pastes[0]


class _LineEditor:
    """Echoes typed keys after the prompt and can take the last one back, also across a wrapped line.
    The cursor is always right after the text, never in the pending-wrap spot at the end of a row."""

    def __init__(self, prompt: str):
        self.prompt = Text.from_markup(f"[bold]{prompt}[/] " if prompt else "")
        self.chars: list[str] = []
        self.times: list[float] = []
        self.can_redraw = True  # the rows above the prompt are still the ones printed before it

    def _width(self) -> int:
        try:
            return os.get_terminal_size(console.file.fileno()).columns
        except (OSError, ValueError, AttributeError):
            return console.width

    def _pos(self) -> int:
        return self.prompt.cell_len + len(self.chars)

    def _write(self, text: str) -> None:
        console.file.write(text)
        if self._pos() and self._pos() % self._width() == 0:
            console.file.write(" \r")  # a row just filled up: go to the start of the next one
        console.file.flush()

    def start(self) -> None:
        console.print(self.prompt, end="", soft_wrap=True)
        self._write("".join(self.chars))

    def add(self, ch: str) -> None:
        self.chars.append(ch)
        self.times.append(time.monotonic())
        self._write(ch)

    def backspace(self) -> None:
        if not self.chars:
            return
        at_row_start = self._pos() % self._width() == 0
        self.chars.pop()
        self.times.pop()
        if at_row_start:  # the last key is at the end of the row above
            console.file.write(f"\x1b[A\x1b[{self._width()}G\x1b[K")
        else:
            console.file.write("\b \b")
        console.file.flush()

    def redraw_above(self, lines: list[str]) -> None:
        """Rewrite the rows just above the prompt (e.g. a live scoreboard) and put the cursor back.
        Each line must fit on one row."""
        if not self.can_redraw or not lines:
            return
        up = len(lines) + self._pos() // self._width()
        console.file.write(f"\x1b7\x1b[{up}A\r" + "".join(f"{line}\x1b[K\x1b[B\r" for line in lines) + "\x1b8")
        console.file.flush()

    def pasted(self, since: float) -> None:
        """Throw away a paste (and the keys just before it that belong to it) and say so."""
        _pastes[0] += 1
        self.can_redraw = False  # the warning now sits between the prompt and what was above it
        cutoff = since - PASTE_START
        while self.times and self.times[-1] >= cutoff:
            self.chars.pop()
            self.times.pop()
        console.file.write("\r\n")
        console.print(f"[bad]{icon('bad')} No pasting![/] [warn]Pasted text is thrown away and counts as "
                      "skipping. Type it yourself.[/]")
        if BUZZ[0]:
            BUZZ[0]()
        self.start()

    def finish(self) -> str:
        console.file.write("\r\n")
        console.file.flush()
        return "".join(self.chars)


def _is_paste(chars: list[str]) -> bool:
    return sum(1 for c in chars if c >= " " and c != "\x7f") > PASTE_BURST


def _typed_keys(chars: list[str], editor: _LineEditor) -> str | None:
    """Apply one batch of typed characters. Returns the line once Enter is pressed."""
    for c in chars:
        if c in "\r\n":
            return editor.finish()
        if c == "\x03":
            raise KeyboardInterrupt
        if c == "\x04" and not editor.chars:
            raise EOFError
        if c in "\b\x7f":
            editor.backspace()
        elif c >= " ":
            editor.add(c)
    return None


IDLE_EVERY = 0.25  # seconds: how often on_idle runs while nothing is typed


def _read_typed_windows(editor: _LineEditor, on_idle=None) -> str:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    hin, hout = kernel32.GetStdHandle(-10), kernel32.GetStdHandle(-11)
    in_mode, out_mode = wintypes.DWORD(), wintypes.DWORD()
    kernel32.GetConsoleMode(hin, ctypes.byref(in_mode))
    if kernel32.GetConsoleMode(hout, ctypes.byref(out_mode)):
        kernel32.SetConsoleMode(hout, out_mode.value | 0x0004)  # understand cursor moves (\x1b[A)
    records, count = (_input_record() * 256)(), wintypes.DWORD()

    def batch() -> list[str]:
        if not kernel32.ReadConsoleInputW(hin, records, 256, ctypes.byref(count)):
            raise EOFError
        return list("".join(r.key.char * max(1, r.key.repeat) for r in records[: count.value]
                            if r.type == 1 and r.key.down and r.key.char != "\x00"))

    # Keys one by one, no echo; Ctrl+C arrives as a key (processed, line, echo and VT input off).
    kernel32.SetConsoleMode(hin, in_mode.value & ~(0x0001 | 0x0002 | 0x0004 | 0x0200))
    try:
        editor.start()
        while True:
            while on_idle and kernel32.WaitForSingleObject(hin, int(IDLE_EVERY * 1000)) != 0:
                on_idle(editor)
            chars = batch()
            if _is_paste(chars):
                since = time.monotonic()
                while kernel32.WaitForSingleObject(hin, int(PASTE_QUIET * 1000)) == 0:
                    batch()  # the rest of the paste
                editor.pasted(since)
                continue
            line = _typed_keys(chars, editor)
            if line is not None:
                return line
    finally:
        kernel32.SetConsoleMode(hin, in_mode.value)


def _read_typed_posix(editor: _LineEditor, on_idle=None) -> str:
    import codecs
    import re
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    escapes = re.compile(r"\x1b(\[[0-9;?]*[ -/]*[@-~]|O.|.)?")  # arrow keys and the like

    def batch() -> str:
        data = os.read(fd, 4096)
        if not data:
            raise EOFError
        return decoder.decode(data)

    try:
        tty.setcbreak(fd)  # keys one by one, no echo; Ctrl+C still stops
        console.file.write("\x1b[?2004h")  # bracketed paste: the terminal marks pasted text
        editor.start()
        while True:
            while on_idle and not select.select([fd], [], [], IDLE_EVERY)[0]:
                on_idle(editor)
            text = batch()
            if "\x1b[200~" in text or _is_paste(list(escapes.sub("", text))):
                since = time.monotonic()
                while select.select([fd], [], [], PASTE_QUIET)[0]:
                    batch()  # the rest of the paste
                editor.pasted(since)
                continue
            line = _typed_keys(list(escapes.sub("", text)), editor)
            if line is not None:
                return line
    finally:
        console.file.write("\x1b[?2004l")
        console.file.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_typed(prompt: str, on_idle=None) -> str:
    """Like input(), but pasted text is thrown away (see PASTE_BURST). on_idle(editor) runs every
    IDLE_EVERY seconds while nothing is typed (e.g. to redraw a live scoreboard with editor.redraw_above)."""
    if not console.is_terminal or not sys.stdin or not sys.stdin.isatty():
        return console.input(f"[bold]{prompt}[/] " if prompt else "")
    editor = _LineEditor(prompt)
    return (_read_typed_windows if os.name == "nt" else _read_typed_posix)(editor, on_idle)


def _read(prompt: str, wait_for_quiet: bool = True, typed: bool = False, on_idle=None) -> str:
    if wait_for_quiet:
        settle()
    try:
        if typed:
            return _read_typed(prompt, on_idle)
        return console.input(f"[bold]{prompt}[/] " if prompt else "")
    except (EOFError, KeyboardInterrupt):
        console.print()
        raise QuitSession from None
    finally:
        _last_key[0] = time.monotonic()
        _tick()


def ask(prompt: str, wait_for_quiet: bool = True, typed: bool = False, on_idle=None) -> str:
    """One line. With typed, pasting is caught (for answers; see paste_count())."""
    value = _read(prompt, wait_for_quiet, typed, on_idle).strip()
    if value.lower() in QUIT_WORDS:
        raise QuitSession
    return value


DONT_KNOW = "?"


def ask_answer(prompt: str, on_idle=None) -> str:
    """An answer to a question. Enter on its own does nothing (so a held Enter can't skip the question);
    '?' means "I don't know" and returns ''. Pasted text is thrown away. on_idle: see _read_typed."""
    while True:
        value = ask(prompt, typed=True, on_idle=on_idle)
        if value == DONT_KNOW:
            return ""
        if value:
            return value
        console.print(f"[hint]Type your answer first, or {DONT_KNOW} if you don't know.[/]")


def ask_multiline(prompt: str) -> str:
    """Several lines of text. A single empty line is kept; two in a row finish.
    Empty lines before any text are ignored; '?' as the first line means "I don't know" and returns ''."""
    console.print(f"[bold]{prompt}[/] [hint](press Enter twice when you're done; {DONT_KNOW} if you don't know)[/]")
    first = ask_answer(">")
    if not first:
        return ""
    lines = [first]
    empty_in_a_row = 0
    while True:
        line = ask("…", wait_for_quiet=False, typed=True)  # no pause between lines: keep typing
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
    hint = "   ".join(f"[key]{escape('[' + ('Enter' if k == '' else k) + ']')}[/] {escape(label)}"
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


# What to do on a screen, as coloured tags under the title, so it's never unclear whether to memorise,
# type, say, listen or read. White on a colour stays readable on dark and light backgrounds.
TODO = {"memorise": "magenta", "type": "blue", "say": "red", "listen": "dark_cyan", "read": "green"}


def todo(*kinds: str, what: str) -> None:
    """E.g. todo("listen", "type", what="Type what you hear.") shows  LISTEN → TYPE  Type what you hear."""
    line = Text()
    for i, kind in enumerate(kinds):
        if i:
            line.append(" → " if FANCY else " > ", style="bold")
        line.append(f" {kind.upper()} ", style=f"bold white on {TODO[kind]}")
    line.append("  " + what, style="bold")
    console.print(line)


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
