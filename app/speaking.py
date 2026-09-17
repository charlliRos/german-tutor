"""Listening and speaking practice: hear the German, record yourself, compare."""
from __future__ import annotations

from . import ui
from .audio import QUIET_PEAK
from .ui import console


def hear(ctx, text: str, slow: bool = True) -> None:
    if ctx.audio.can_speak:
        with console.status("[dim]▶ speaking…[/]"):
            ctx.audio.say(text, slow)


def _record(ctx, long_text: bool):
    if long_text:
        ui.ask("Press Enter, then read the text out loud.")
        console.print("[bold red]● Recording…[/] press Enter when you're finished.")
        recording = ctx.audio.record_until(lambda: ui.ask(""))
    else:
        seconds = ctx.settings["word_record_seconds"]
        ui.ask("Press Enter, then say it.")
        with console.status(f"[bold red]● Recording for {seconds} seconds, speak now![/]"):
            recording = ctx.audio.record_seconds(seconds)
    if recording[0].size == 0:
        console.print("[yellow]I couldn't hear anything. Is the microphone muted or too far away?[/]")
        return None
    if ctx.audio.last_peak < QUIET_PEAK:
        console.print("[dim yellow]Your mic is very quiet. Speak closer, or turn up the microphone level "
                      "in your sound settings.[/]")
    return recording


def _play_both(ctx, recording, text: str, slow: bool) -> None:
    if recording is not None:
        console.print("[magenta]▶ You[/]")
        ctx.audio.play(*recording)
    console.print("[cyan]▶ Correct[/]")
    hear(ctx, text, slow)


def speak_and_compare(ctx, text: str, long_text: bool = False) -> None:
    """The kid says `text`; then their recording and the correct pronunciation play back to back."""
    slow = not long_text
    while True:
        if ctx.audio.can_record:
            recording = _record(ctx, long_text)
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
