"""Listening and speaking practice: hear the German, record yourself, compare."""
from __future__ import annotations

from . import ui
from .audio import QUIET_PEAK
from .ui import console, icon


def hear(ctx, text: str, slow: bool = True) -> None:
    """Play the German. Enter skips it, Ctrl+C stops it; neither leaks into the next prompt."""
    if not ctx.audio.can_speak:
        return
    try:
        with console.status(f"[hint]{icon('play')} speaking… (Enter to skip)[/]"):
            ctx.audio.say(text, slow, stop_when=ui.key_pressed)
    except KeyboardInterrupt:
        console.print("[hint](stopped)[/]")
    ui.flush_input()


def record_seconds_for(ctx, text: str) -> float:
    """Long enough for phrases: at least the configured time, more for longer text (max 10 s)."""
    return round(min(10.0, max(float(ctx.settings["word_record_seconds"]), 1.5 + 0.12 * len(text))), 1)


def _record(ctx, text: str, long_text: bool):
    try:
        if long_text:
            ui.ask(f"{icon('mic')} Press Enter, then read the text out loud.")
            console.print(f"[rec]{icon('rec')} Recording…[/] press Enter when you're finished.")
            recording = ctx.audio.record_until(lambda: ui.ask(""))
        else:
            seconds = record_seconds_for(ctx, text)
            ui.ask(f"{icon('mic')} Press Enter, then say it.")
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


def speak_and_compare(ctx, text: str, long_text: bool = False, slow: bool | None = None) -> None:
    """The kid says `text`; then their recording and the reference pronunciation play back to back.
    Single words play slowly, texts at normal speed (unless `slow` says otherwise)."""
    slow = not long_text if slow is None else slow
    while True:
        if ctx.audio.can_record:
            recording = _record(ctx, text, long_text)
        else:
            ui.ask("Say it out loud now, then press Enter to hear how it should sound.")
            recording = None
        _play_both(ctx, recording, text, slow)

        options = {"": "next", "r": "play again" if recording is not None else "hear it again"}
        if ctx.audio.can_record:
            options["a"] = "try again"
        while True:
            choice = ui.keys(options)
            if choice == "":
                return
            if choice == "a":
                break
            _play_both(ctx, recording, text, slow)
