"""Startup banner: Fritz the Dackel (German) with Pip the robin (English) on his back."""
from __future__ import annotations

import random

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DOG, BIRD, BREAST, EYE = "#c8894a", "#8a6a4f", "#ff6b3d", "bold white"

# Each line is a list of (text, style) pieces so the dog and the bird get their own colours.
EAR, NOSE = "#8b5a2b", "bold #3b2a1a"

ART = [
    [("                    ", ""), (",_", BIRD)],
    [("                   ", ""), ("(", BIRD), ("o", EYE), (" >", BIRD)],
    [("                   ", ""), ("/", BIRD), (")", BREAST), ("_)", BIRD), ("      __", EAR)],
    [(" (\\,----------------", DOG), ('""', BIRD), ("------'", DOG), ("()", EAR), ("'--", DOG), ("o", NOSE)],
    [("  (_     _______________     /~\"", DOG)],
    [("   (_)_)                (_)_)", DOG)],
]

GREETINGS = [
    ("Hallo, {name}!", "Hello, {name}!"),
    ("Schön, dich zu sehen, {name}!", "Nice to see you, {name}!"),
    ("Na, {name}, bereit?", "Well, {name}, ready?"),
    ("Los geht's, {name}!", "Let's go, {name}!"),
    ("Guten Tag, {name}!", "Good day, {name}!"),
]


def flag() -> Text:
    return Text.assemble(("━━━", "#555555"), ("━━━", "#dd0000"), ("━━━", "#ffce00"))


def banner(name: str | None = None, facts: list[str] | None = None) -> Panel:
    art = Text("\n").join(Text.assemble(*line) for line in ART)

    side = Text()
    side.append("Deutsch mit Fritz & Pip\n", style="bold")
    side.append_text(flag())
    side.append("\n\n")
    if name:
        de, en = random.choice(GREETINGS)
        side.append(de.format(name=name) + "\n", style="bold cyan")
        side.append(en.format(name=name) + "\n", style="green")
    else:
        side.append("Wer lernt heute?\n", style="bold cyan")
        side.append("Who's learning today?\n", style="green")
    for fact in facts or []:
        side.append("\n" + fact, style="dim")

    grid = Table.grid(padding=(0, 3))
    grid.add_column(no_wrap=True)
    grid.add_column()
    grid.add_row(art, side)
    return Panel(grid, border_style="#ffce00", padding=(1, 2), expand=False)
