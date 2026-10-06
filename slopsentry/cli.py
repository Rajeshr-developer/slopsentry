"""SlopSentry command-line interface."""

import asyncio
from collections.abc import Callable

import typer
from rich.console import Console

from slopsentry.checks import CheckResult
from slopsentry.checks.age import check_age
from slopsentry.checks.exists import check_exists
from slopsentry.registry import PyPIClient

app = typer.Typer(help="Check packages for slopsquatting before they are installed.")
console = Console()

# Tests replace this to inject a client backed by a mock transport.
client_factory: Callable[[], PyPIClient] = PyPIClient

# Warnings don't affect the exit code until scoring lands.
EXIT_CODES = {"pass": 0, "warn": 0, "fail": 1, "error": 2}
STYLES = {"pass": "green", "warn": "yellow", "fail": "red", "error": "yellow"}


async def _run_checks(package: str) -> list[CheckResult]:
    client = client_factory()
    try:
        results = [await check_exists(package, client)]
        if results[0][0] == "pass":
            results.append(await check_age(package, client))
        return results
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
    """Check that PACKAGE exists on PyPI and doesn't look freshly registered."""
    exit_code = 0
    for status, detail, _points in asyncio.run(_run_checks(package)):
        if status == "error" and not strict:
            console.print(
                f"[yellow]WARN[/yellow] {package}: {detail} (allowing; use --strict to block)"
            )
            continue
        style = STYLES[status]
        console.print(f"[{style}]{status.upper()}[/{style}] {package}: {detail}")
        exit_code = max(exit_code, EXIT_CODES[status])
    raise typer.Exit(exit_code)
