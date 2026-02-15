"""Centralized Rich console and display helpers for the n1-brightdata CLI."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

THEME = Theme(
    {
        "brand": "bold bright_cyan",
        "step": "bold yellow",
        "success": "bold green",
        "error": "bold red",
        "info": "dim cyan",
        "url": "underline blue",
        "warning": "bold yellow",
        "muted": "dim white",
    }
)

console = Console(theme=THEME)


def print_banner() -> None:
    banner = Text()
    banner.append("n1-brightdata", style="bold bright_cyan")
    banner.append("  Browser Agent", style="dim white")
    console.print(
        Panel(banner, border_style="bright_cyan", padding=(0, 2)),
    )


def print_config_summary(
    task: str, url: str, max_steps: int, model: str,
) -> None:
    table = Table(show_header=False, border_style="dim", padding=(0, 1))
    table.add_column("Key", style="info")
    table.add_column("Value", style="white")
    table.add_row("Task", task)
    table.add_row("Start URL", url)
    table.add_row("Max steps", str(max_steps))
    table.add_row("Model", model)
    console.print(table)
    console.print()


def print_step(step_num: int, max_steps: int, assistant_text: str) -> None:
    header = Text()
    header.append(f"Step {step_num}/{max_steps}", style="step")
    header.append("  ", style="")
    display = assistant_text or "[no text]"
    if len(display) > 300:
        display = display[:300] + "..."
    header.append(display, style="white")
    console.print(header)


def print_tool_action(tool_name: str, args_summary: str) -> None:
    console.print(f"  [info]> {tool_name}[/info] {escape(args_summary)}", highlight=False)


def print_trim_notice(removed: int, size_mb: float, *, retry: bool = False) -> None:
    prefix = "Retrying after extra trim" if retry else "Trimmed"
    console.print(
        f"  [warning]{prefix} {removed} old screenshot(s); "
        f"payload ~{size_mb:.2f} MB[/warning]"
    )


def print_early_stop() -> None:
    console.print("\n[success]Early stop:[/success] sufficient information collected.\n")


def print_done() -> None:
    console.print("[success]Done.[/success]\n")


def print_final_answer(answer: str) -> None:
    console.print()
    console.print(
        Panel(
            answer,
            title="[success]Final Answer[/success]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def print_error(message: str) -> None:
    console.print(
        Panel(
            f"[error]{escape(message)}[/error]",
            title="Error",
            border_style="red",
        )
    )


def status_spinner(message: str) -> "Console.status":
    return console.status(message, spinner="dots")
