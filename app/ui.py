"""Small terminal helpers on top of rich."""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)

QUIT_WORDS = {":q", ":quit", ":exit"}
UMLAUT_TIP = "[dim]No ä ö ü ß on your keyboard? Type ae oe ue ss. Type :q to stop.[/]"


class QuitSession(Exception):
    """The user typed :q (or closed input) to leave the current activity."""


def ask(prompt: str) -> str:
    try:
        value = console.input(f"[bold]{prompt}[/] ")
    except EOFError:
        raise QuitSession from None
    if value.strip().lower() in QUIT_WORDS:
        raise QuitSession
    return value.strip()


def ask_multiline(prompt: str) -> str:
    console.print(f"[bold]{prompt}[/] [dim](press Enter on an empty line when you're done)[/]")
    lines = []
    while True:
        line = ask("…" if lines else ">")
        if not line:
            return " ".join(lines)
        lines.append(line)


def keys(options: dict[str, str]) -> str:
    """Show e.g. '[Enter] next  [r] hear again' and return the chosen key ('' is Enter)."""
    hint = "   ".join(f"[cyan]{escape('[' + ('Enter' if k == '' else k) + ']')}[/] {label}"
                      for k, label in options.items())
    while True:
        console.print(hint)
        choice = ask(">").lower()
        if choice in options:
            return choice
        console.print("[dim]Pick one of the options above.[/]")


def title(heading: str, sub: str = "") -> None:
    console.rule(f"[bold]{escape(heading)}[/]" + (f"  [dim]{escape(sub)}[/]" if sub else ""))


def german(text: str, heading: str = "Deutsch", subtitle: str | None = None) -> Panel:
    return Panel(Text(text, style="bold cyan"), title=heading, subtitle=subtitle,
                 border_style="cyan", padding=(1, 2))


def english(text: str, heading: str = "English") -> Panel:
    return Panel(Text(text, style="green"), title=heading, border_style="green", padding=(1, 2))


def side_by_side(left_title: str, left: str, right_title: str, right: str) -> None:
    left = left or "(nothing written)"
    if console.width < 80:
        console.print(Panel(Text(left), title=left_title, border_style="magenta"))
        console.print(Panel(Text(right), title=right_title, border_style="cyan"))
        return
    table = Table(box=box.ROUNDED, expand=True, show_lines=False, padding=(1, 2))
    table.add_column(left_title, ratio=1, style="magenta")
    table.add_column(right_title, ratio=1, style="cyan")
    table.add_row(Text(left), Text(right))
    console.print(table)
