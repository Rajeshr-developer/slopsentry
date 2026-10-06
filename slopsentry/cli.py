"""SlopSentry command-line interface."""

import asyncio
from collections.abc import Callable

import typer
from rich.console import Console

from slopsentry.checks import CheckResult
from slopsentry.checks.exists import check_exists
from slopsentry.registry import PyPIClient

app = typer.Typer(help="Check packages for slopsquatting before they are installed.")
console = Console()

# Tests replace this to inject a client backed by a mock transport.
client_factory: Callable[[], PyPIClient] = PyPIClient

EXIT_CODES = {"pass": 0, "fail": 1, "error": 2}
STYLES = {"pass": "green", "fail": "red", "error": "yellow"}


async def _run_check(package: str) -> CheckResult:
    client = client_factory()
    try:
        return await check_exists(package, client)
    finally:
        await client.aclose()


@app.callback()
def main() -> None:
    """Check packages for slopsquatting before they are installed."""


@app.command()
def check(
    package: str = typer.Argument(..., help="Package name to check."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit 2 instead of warning when the registry is unreachable."
    ),
) -> None:
    """Verify that PACKAGE exists on PyPI."""
    status, detail, _points = asyncio.run(_run_check(package))
    if status == "error" and not strict:
        console.print(
            f"[yellow]WARN[/yellow] {package}: {detail} (allowing; use --strict to block)"
        )
        raise typer.Exit(0)
    style = STYLES[status]
    console.print(f"[{style}]{status.upper()}[/{style}] {package}: {detail}")
    raise typer.Exit(EXIT_CODES[status])
