from pathlib import Path
import json
import subprocess
import sys

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from .agent import build_agent_config, run_agent
from .console import console, print_error, status_spinner

CREDENTIALS_PATH = Path.home() / ".n1-brightdata" / "credentials.json"


class DefaultRunGroup(click.Group):
    """Click group that routes bare args to the `run` command."""

    default_command = "run"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args:
            first = args[0]
            if first not in ("-h", "--help") and first not in self.commands:
                args.insert(0, self.default_command)
        else:
            args.insert(0, self.default_command)
        return super().parse_args(ctx, args)


@click.group(cls=DefaultRunGroup)
def main() -> None:
    """n1-brightdata CLI."""


@main.command("run")
@click.argument("task", required=True)
@click.option(
    "--url",
    default="https://www.google.com",
    show_default=True,
    help="Initial URL to open before the agent loop starts.",
)
@click.option(
    "--max-steps",
    type=click.IntRange(min=1),
    default=30,
    show_default=True,
    help="Maximum number of tool-using iterations.",
)
@click.option(
    "--screenshot-format",
    type=click.Choice(["jpeg", "png"], case_sensitive=False),
    default="jpeg",
    show_default=True,
    help="Screenshot format sent to the model.",
)
@click.option(
    "--jpeg-quality",
    type=click.IntRange(1, 100),
    default=60,
    show_default=True,
    help="JPEG quality used when --screenshot-format=jpeg.",
)
@click.option(
    "--screenshot-timeout-ms",
    type=click.IntRange(min=1),
    default=90_000,
    show_default=True,
    help="Timeout for Playwright page screenshots in milliseconds.",
)
@click.option(
    "--show-inspect-url",
    is_flag=True,
    default=False,
    help="Print a DevTools inspect URL for the live browser session.",
)
@click.option(
    "--yutori-api-key",
    envvar="YUTORI_API_KEY",
    show_envvar=True,
    default=None,
    help="Yutori API key.",
)
@click.option(
    "--brd-cdp-url",
    envvar="BRD_CDP_URL",
    show_envvar=True,
    default=None,
    help="Bright Data Scraping Browser CDP WebSocket URL.",
)
@click.option(
    "--env-file",
    type=click.Path(path_type=Path, dir_okay=False, resolve_path=True),
    default=None,
    help="Path to a .env file. Defaults to ./.env when omitted.",
)
def run(
    task: str,
    url: str,
    max_steps: int,
    screenshot_format: str,
    jpeg_quality: int,
    screenshot_timeout_ms: int,
    show_inspect_url: bool,
    yutori_api_key: str | None,
    brd_cdp_url: str | None,
    env_file: Path | None,
) -> None:
    """Run the n1 Bright Data browser agent."""
    try:
        config = build_agent_config(
            env_file=env_file,
            yutori_api_key=yutori_api_key,
            brd_cdp_url=brd_cdp_url,
            screenshot_format=screenshot_format,
            jpeg_quality=jpeg_quality,
            screenshot_timeout_ms=screenshot_timeout_ms,
        )
        run_agent(
            task=task,
            start_url=url,
            max_steps=max_steps,
            config=config,
            show_inspect_url=show_inspect_url,
        )
    except RuntimeError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc



def _wizard_step_header(step: int, total: int, title: str) -> None:
    console.print()
    console.rule(f"[step]Step {step} of {total}[/step]  {title}", style="dim")
    console.print()


def _read_credentials() -> dict[str, str]:
    if not CREDENTIALS_PATH.exists():
        return {}
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str)}
    except Exception:
        return {}


def _write_credentials(values: dict[str, str]) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "YUTORI_API_KEY": values.get("YUTORI_API_KEY", ""),
        "BRD_CDP_URL": values.get("BRD_CDP_URL", ""),
    }
    CREDENTIALS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    CREDENTIALS_PATH.chmod(0o600)


def _mask(value: str) -> str:
    if len(value) > 8:
        return value[:4] + "****" + value[-4:]
    return "****"


def _test_yutori(api_key: str) -> bool:
    try:
        from openai import OpenAI

        client = OpenAI(base_url="https://api.yutori.com/v1", api_key=api_key)
        client.models.list()
        return True
    except Exception:
        return False


def _test_brightdata(cdp_url: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            browser.close()
        return True
    except Exception:
        return False



@main.command("setup")
def setup() -> None:
    """Interactive setup wizard -- credentials, Playwright, and connectivity."""
    total = 5

    # Banner
    console.print()
    console.print(
        Panel(
            "[brand]n1-brightdata[/brand]  [muted]Setup Wizard[/muted]",
            border_style="bright_cyan",
            padding=(0, 2),
        )
    )

    env_values = _read_credentials()

    # -- Step 1: Bright Data ------------------------------------------------
    _wizard_step_header(1, total, "Bright Data Scraping Browser")

    existing_brd = env_values.get("BRD_CDP_URL", "").strip()
    use_existing_brd = False
    if existing_brd and existing_brd != "YOUR_CDP_URL":
        console.print(f"  [success]Found existing Bright Data CDP URL[/success]  [muted]{_mask(existing_brd)}[/muted]")
        use_existing_brd = Confirm.ask("  Use existing URL?", default=True, console=console)

    if not use_existing_brd:
        console.print("  You need a Bright Data [bold]Scraping Browser[/bold] zone.\n")
        console.print("  1. Sign up or log in at:")
        console.print("     [url]https://brightdata.com[/url]\n")
        console.print("  2. Go to the dashboard and create a new")
        console.print("     [bold]Scraping Browser[/bold] zone.\n")
        console.print("  3. Copy the CDP WebSocket URL (starts with wss://).\n")
        brd_cdp_url = Prompt.ask("  Paste your Bright Data CDP URL", console=console)
        env_values["BRD_CDP_URL"] = brd_cdp_url.strip()
        console.print("  [success]Bright Data CDP URL saved.[/success]")

    _wizard_step_header(2, total, "Yutori API Key")

    existing_yt = env_values.get("YUTORI_API_KEY", "").strip()
    use_existing_yt = False
    if existing_yt and existing_yt != "YOUR_API_KEY":
        console.print(f"  [success]Found existing Yutori API key[/success]  [muted]{_mask(existing_yt)}[/muted]")
        use_existing_yt = Confirm.ask("  Use existing key?", default=True, console=console)

    if not use_existing_yt:
        console.print("  You need a Yutori API key.\n")
        console.print("  1. Sign up or log in at:")
        console.print("     [url]https://yutori.com[/url]\n")
        console.print("  2. Navigate to API keys and create one.\n")
        yt_key = Prompt.ask("  Paste your Yutori API key", console=console)
        env_values["YUTORI_API_KEY"] = yt_key.strip()
        console.print("  [success]Yutori API key saved.[/success]")

    _wizard_step_header(3, total, "Save Configuration")

    with status_spinner("Writing credentials..."):
        _write_credentials(env_values)
    console.print(f"  [success]Saved credentials[/success] to [muted]{CREDENTIALS_PATH}[/muted]")

    _wizard_step_header(4, total, "Install Playwright")

    try:
        with status_spinner("Installing Playwright Chromium..."):
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
            )
        console.print("  [success]Playwright Chromium is ready.[/success]")
    except subprocess.CalledProcessError as exc:
        print_error(
            f"Failed to install Playwright Chromium (exit code {exc.returncode})."
        )
        raise SystemExit(1) from exc

    _wizard_step_header(5, total, "Verify Connectivity")

    if Confirm.ask("  Test credentials now?", default=True, console=console):
        # Yutori
        with status_spinner("Testing Yutori API connection..."):
            yt_ok = _test_yutori(env_values.get("YUTORI_API_KEY", ""))
        if yt_ok:
            console.print("  [success]Yutori API: connected[/success]")
        else:
            console.print("  [error]Yutori API: connection failed. Check your API key.[/error]")

        # Bright Data
        with status_spinner("Testing Bright Data browser connection..."):
            brd_ok = _test_brightdata(env_values.get("BRD_CDP_URL", ""))
        if brd_ok:
            console.print("  [success]Bright Data: connected successfully[/success]")
        else:
            console.print("  [error]Bright Data: connection failed. Check your password.[/error]")
    else:
        console.print("  [muted]Skipped connectivity check.[/muted]")

    console.print()
    console.print(
        Panel(
            "[success]Setup complete![/success]\n\n"
            "Run your first task:\n"
            '[bold]n1-brightdata "Search for latest news"[/bold]',
            border_style="green",
            padding=(1, 2),
        )
    )


if __name__ == "__main__":
    main()
