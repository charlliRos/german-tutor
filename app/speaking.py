"""Listening and speaking practice: hear the German, record yourself, compare."""
from __future__ import annotations

import time

from . import ui
from .audio import QUIET_PEAK
from .listen import said_it
from .ui import console, icon


FEMALE = {"frau", "mutter", "mama", "oma", "tante", "schwester", "tochter", "mädchen", "lehrerin", "verkäuferin",
          "moderatorin", "ärztin", "chefin", "kellnerin", "kundin", "sprecherin", "reporterin", "freundin", "gastmutter"}
MALE = {"mann", "herr", "vater", "papa", "opa", "onkel", "bruder", "sohn", "junge", "lehrer", "verkäufer",
        "moderator", "arzt", "chef", "kellner", "kunde", "sprecher", "reporter", "freund", "gastvater"}
FEMALE_NAMES = {"lena", "anna", "sophie", "emma", "maya", "lea", "mia", "julia", "sarah", "petra", "aylin", "sandra",
                "laura", "lisa", "marie", "hannah", "nina", "clara", "frieda", "greta", "katrin", "jana", "ayşe"}


def voices_for(speakers: list[str]) -> dict[str, str]:
    """A voice per speaker of a conversation: women and girls higher, a second man lower, so the speakers can be
    told apart (all from the one German voice)."""
    out, men, women = {}, 0, 0
    for who in dict.fromkeys(speakers):
        words = who.lower().replace("-", " ").split()
        female = any(w in FEMALE or w in FEMALE_NAMES for w in words) or (
            words and not any(w in MALE for w in words) and words[-1].endswith(("a", "ie", "ine")))
        if female:
            out[who], women = ("high", "higher")[women % 2], women + 1
        else:
            out[who], men = ("", "low")[men % 2], men + 1
    return out


def hear_lines(ctx, lines: list[dict]) -> None:
    """Play a conversation ([{"who", "de"}]), each speaker in their own voice. Enter skips it."""
    if not ctx.audio.can_speak:
        return
    voices = voices_for([line.get("who", "") for line in lines])
    try:
        with console.status(f"[hint]{icon('play')} playing… (Enter to skip)[/]"):
            ctx.audio.say_lines([(voices[line.get("who", "")], line["de"]) for line in lines], stop_when=ui.key_pressed)
    except KeyboardInterrupt:
        console.print("[hint](stopped)[/]")
    ui.drop_enters()


def hear(ctx, text: str, slow: bool = True, voice: str = "") -> None:
    """Play the German. Enter skips it, Ctrl+C stops it; neither leaks into the next prompt."""
    if not ctx.audio.can_speak:
        return
    try:
        with console.status(f"[hint]{icon('play')} speaking… (Enter to skip)[/]"):
            ctx.audio.say(text, slow, stop_when=ui.key_pressed, **({"voice": voice} if voice else {}))
    except KeyboardInterrupt:
        console.print("[hint](stopped)[/]")
    ui.drop_enters()  # an answer typed while the word was playing is kept


def record_for(ctx, seconds: float):
    """Countdown, then record for `seconds` (a speaking task). The recording, or None."""
    try:
        _countdown(ctx)
        with console.status("") as status:
            def tick(left: float) -> bool:
                status.update(f"[rec]{icon('rec')} Recording, speak now! {left:0.0f} s left[/] [hint](Enter = done)[/]")
                return ui.key_pressed()
            recording = ctx.audio.record_seconds(seconds, on_tick=tick)
        ui.flush_input()
    except KeyboardInterrupt:
        ctx.audio.sd.stop()
        return None
    return recording if recording[0].size else None


def record_seconds_for(ctx, text: str) -> float:
    """Long enough for phrases: at least the configured time, more for longer text (max 10 s)."""
    return round(min(10.0, max(float(ctx.settings["word_record_seconds"]), 1.5 + 0.12 * len(text))), 1)


AUTO_NEXT_HEARD = 3    # seconds after a speaking turn the speech check heard, then on to the next
COUNTDOWN = 3          # "3 · 2 · 1 · speak!" before recording starts by itself (no Enter needed)
COUNTDOWN_STEP = 0.45  # seconds per number


def _countdown(ctx) -> None:
    """Get ready, then a beep: recording starts by itself, so nobody misses that it began."""
    with console.status("") as status:
        for n in range(COUNTDOWN, 0, -1):
            status.update(f"[rec]{icon('mic')} Get ready to speak… {n}[/]")
            time.sleep(COUNTDOWN_STEP)
    from . import sfx
    sfx.play(ctx.audio, "go")
    ui.flush_input()


def _record(ctx, text: str, long_text: bool):
    try:
        if long_text:
            _countdown(ctx)
            console.print(f"[rec]{icon('rec')} Recording, read it out loud now![/] Press Enter when you're finished.")
            recording = ctx.audio.record_until(lambda: ui.ask(""))
        else:
            seconds = record_seconds_for(ctx, text)
            _countdown(ctx)
            with console.status("") as status:
                def tick(left: float) -> bool:
                    status.update(f"[rec]{icon('rec')} Recording, speak now! {left:0.1f} s left[/]")
                    return False
                recording = ctx.audio.record_seconds(seconds, on_tick=tick)
            ui.flush_input()
    except KeyboardInterrupt:
        ctx.audio.sd.stop()
        console.print("[hint](recording stopped)[/]")
        return None
    if recording[0].size == 0:
        console.print("[warn]I couldn't hear anything. Is the microphone muted or too far away?[/]")
        return None
    if ctx.audio.last_peak < QUIET_PEAK:
        console.print("[warn]Your mic is very quiet. Speak closer, or turn up the microphone level "
                      "in your sound settings.[/]")
    return recording


def _play_both(ctx, recording, text: str, slow: bool) -> None:
    if recording is not None:
        console.print(f"[magenta]{icon('play')} Your recording[/]")
        try:
            ctx.audio.play(*recording, stop_when=ui.key_pressed)
        except KeyboardInterrupt:
            pass
        ui.flush_input()
    console.print(f"[cyan]{icon('play')} How it should sound[/]")
    hear(ctx, text, slow)


def _check_speech(ctx, recording, text: str) -> bool:
    """Show what the speech checker heard. True if it sounds like `text`."""
    with console.status("[hint]Listening to your recording…[/]"):
        heard = ctx.audio.heard(*recording)
    if not heard:
        console.print(f"[warn]{icon('bad')} I didn't catch any words.[/] [hint]Speak clearly, close to the mic.[/]")
        return False
    if said_it(heard, text):
        console.print(f"[good]{icon('ok')} I heard:[/] [de]{ui.escape(heard)}[/]")
        return True
    console.print(f"[warn]{icon('almost')} I heard:[/] [de]{ui.escape(heard)}[/] "
                  "[hint]That doesn't sound like it yet. Press a to try again.[/]")
    return False


def speak_and_compare(ctx, text: str, long_text: bool = False, slow: bool | None = None,
                      must_say: bool = False, reveal: bool = False) -> bool:
    """The kid says `text`; then their recording and the reference pronunciation play back to back.
    Single words play slowly, texts at normal speed (unless `slow` says otherwise).
    Returns True if the speech checker heard it (or can't check: no mic or no checker).
    must_say: it counts (a look back, a speaking turn): say so if it wasn't heard, and count it for the report.
    reveal: the text wasn't on screen (said from memory): show it when the right pronunciation plays."""
    slow = not long_text if slow is None else slow
    checking = ctx.audio.can_record and ctx.audio.can_check_speech
    said = not checking
    while True:
        if ctx.audio.can_record:
            recording = _record(ctx, text, long_text)
        else:
            ui.ask("Say it out loud now, then press Enter to hear how it should sound.")
            recording = None
        if checking:
            said = (recording is not None and _check_speech(ctx, recording, text)) or said
        if reveal:
            console.print(ui.german(text, "It's", word=not long_text))
            reveal = False
        _play_both(ctx, recording, text, slow)

        options = {"": "next", "r": "play again" if recording is not None else "hear it again"}
        if ctx.audio.can_record:
            options["a"] = "try again"
        auto = checking and said  # heard: go on by itself (a key stops the clock to replay or try again)
        while True:
            choice = ui.timed_keys(options, AUTO_NEXT_HEARD) if auto else ui.keys(options)
            auto = False
            if choice == "":
                if must_say and checking:
                    ctx.profile.count(ctx.today, speaking=1, speaking_heard=int(said))
                    if not said:
                        console.print("[hint]Not heard, so this one doesn't count yet.[/]")
                return said
            if choice == "a":
                break
            _play_both(ctx, recording, text, slow)
