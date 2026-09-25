"""A kid's goal (A2, B1 or C1) and favourite topics: which new words come first (docs/LEARNING_DESIGN.md 3.2).

The goal caps the level of new words and sets the mix of everyday / official / STEM words; the topics
the kid picks go first among words that are about equally common. Asked once, changed in "My progress".
"""
from __future__ import annotations

from rich.table import Table

from . import ui
from .ui import console

TRACKS = {
    "A2": {"label": "A2: everyday German first (the first exam)", "levels": {"A1", "A2"}, "extra": 200,
           "shares": {"daily": 0.9, "admin": 0.05, "stem": 0.05}},
    "B1": {"label": "B1: German for working in Germany", "levels": {"A1", "A2", "B1"}, "extra": 200,
           "shares": {"daily": 0.7, "admin": 0.2, "stem": 0.1}},
    "C1": {"label": "C1: German for studying at a German university", "levels": None, "extra": 0,
           "shares": {"daily": 0.5, "admin": 0.2, "stem": 0.3}},
}
TOPICS = ["free-time", "sport", "music", "food", "travel", "technology", "media", "social", "texting", "slang",
          "school", "animals", "clothing", "shopping", "health", "feelings", "family", "nature", "city", "work"]
MAX_TOPICS = 4


def settings_for(settings: dict, data: dict) -> dict:
    """The settings with the goal's word mix (the config's bank_shares when no goal is set)."""
    track = TRACKS.get(data.get("target"))
    return {**settings, "bank_shares": track["shares"]} if track else settings


def allowed_words(words: dict, data: dict) -> set[str] | None:
    """Word ids new words may come from under the kid's goal: its levels plus the next `extra` most common
    words above them (so a kid near the level isn't held back). None = no limit."""
    track = TRACKS.get(data.get("target"))
    if not track or track["levels"] is None:
        return None
    inside = {w.id for w in words.values() if w.level in track["levels"] or not w.level}
    above = sorted((w for w in words.values() if w.id not in inside), key=lambda w: (w.rank, w.id))
    return inside | {w.id for w in above[: track["extra"]]}


def topics(data: dict) -> tuple[str, ...]:
    return tuple(t for t in data.get("topics", []) if t in TOPICS)


def choose(ctx) -> None:
    """Ask for the goal and up to four topics; saves them in the profile."""
    ui.clear()
    ui.title("Your goal")
    console.print("What are you learning German for? It decides which new words come first. "
                  "[hint](You can change it any time in My progress.)[/]\n")
    for key, (level, track) in zip(("", "b", "c"), TRACKS.items()):
        console.print(f"  [key]{'Enter' if not key else key}[/]  {track['label']}")
    choice = ui.keys({"": "A2", "b": "B1", "c": "C1"})
    ctx.profile.data["target"] = {"": "A2", "b": "B1", "c": "C1"}[choice]
    ui.clear()
    ui.title("Your topics")
    console.print(f"Pick up to {MAX_TOPICS} topics you like: their words come first.\n")
    grid = Table.grid(padding=(0, 3))
    for _ in range(4):
        grid.add_column()
    cells = [f"[key]{n}[/] {topic}" for n, topic in enumerate(TOPICS, 1)]
    for row in range(0, len(cells), 4):
        grid.add_row(*cells[row:row + 4])
    console.print(grid)
    answer = ui.ask(f"Numbers, e.g. 1 3 6 (Enter = no favourites):", wait_for_quiet=False)
    picked = []
    for token in answer.replace(",", " ").split():
        if token.isdigit() and 1 <= int(token) <= len(TOPICS) and TOPICS[int(token) - 1] not in picked:
            picked.append(TOPICS[int(token) - 1])
    ctx.profile.data["topics"] = picked[:MAX_TOPICS]
    ctx.profile.save()
    console.print(f"[good]Goal {ctx.profile.data['target']}"
                  + (f", topics: {', '.join(picked[:MAX_TOPICS])}" if picked else "") + ".[/]")
    ui.keys({"": "continue"})
