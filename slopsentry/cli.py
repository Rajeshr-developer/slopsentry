"""SlopSentry command-line interface."""

import asyncio
import json
import sys
from collections.abc import Callable

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from slopsentry import hook as hook_mod
from slopsentry.registry import PyPIClient
from slopsentry.scoring import BLOCK_AT, WARN_AT, Report, score
from slopsentry.spec import InvalidPackageSpec, parse_package_name

app = typer.Typer(help="Check packages for slopsquatting before they are installed.")
console = Console()
err_console = Console(stderr=True)

# Tests replace these to inject a client backed by a mock transport.
client_factory: Callable[[], PyPIClient] = PyPIClient


def hook_client_factory() -> PyPIClient:
    return PyPIClient(timeout=hook_mod.HOOK_TIMEOUT)


VERDICT_EXIT = {"pass": 0, "warn": 0, "block": 1}
STRICT_ERROR_EXIT = 2
INVALID_INPUT_EXIT = 2

VERDICT_STYLES = {"pass": "green", "warn": "yellow", "block": "red", "error": "red"}
STATUS_STYLES = {"pass": "green", "warn": "yellow", "skip": "dim", "fail": "red", "error": "yellow"}


async def _score(package: str) -> Report:
    client = client_factory()
    try:
        return await score(package, client)
    finally:
        await client.aclose()


def _print_table(report: Report) -> None:
    table = Table(title=f"SlopSentry: {escape(report.package)}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_column("Points", justify="right")
    for r in report.results:
        style = STATUS_STYLES[r.status]
        table.add_row(r.check, f"[{style}]{r.status}[/{style}]", escape(r.detail), str(r.points))
    console.print(table)
    console.print(f"Total: {report.total} points (warn at {WARN_AT}, block at {BLOCK_AT})")


def _print_summary(report: Report, strict_error: bool, with_reasons: bool) -> None:
    label = "error" if strict_error else report.verdict
    style = VERDICT_STYLES[label]
    line = f"[{style}]{label.upper()}[/{style}] {escape(report.package)}: score {report.total}"
    if strict_error:
        line += ", could not be verified (--strict)"
    elif report.has_errors:
        line += ", could not be fully verified (allowing; use --strict to block)"
    console.print(line)

    if with_reasons and label != "pass":
        for r in report.reasons:
            console.print(f"  - {r.check}: {escape(r.detail)} (+{r.points})")


@app.callback()
def main() -> None:
    """Check packages for slopsquatting before they are installed."""


@app.command()
def check(
    spec: str = typer.Argument(
        ..., metavar="PACKAGE", help="Package name or requirement, e.g. requests[socks]==2.31.0."
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Exit 2 instead of warning when the registry is unreachable."
    ),
    explain: bool = typer.Option(
        False, "--explain", help="Show every check's status, detail and points."
    ),
) -> None:
    """Score PACKAGE for slopsquatting risk: pass, warn or block."""
    try:
        package = parse_package_name(spec)
    except InvalidPackageSpec as exc:
        err_console.print(f"[red]ERROR[/red] {escape(str(exc))}", highlight=False)
        raise typer.Exit(INVALID_INPUT_EXIT) from None

    report = asyncio.run(_score(package))
    strict_error = strict and report.has_errors

    if explain:
        _print_table(report)
    _print_summary(report, strict_error, with_reasons=not explain)

    raise typer.Exit(STRICT_ERROR_EXIT if strict_error else VERDICT_EXIT[report.verdict])


@app.command()
def hook(
    debug: bool = typer.Option(False, "--debug", help="Also print swallowed exceptions to stderr."),
) -> None:
    """Claude Code PreToolUse hook: read the event on stdin, print a decision as JSON.

    Always exits 0. Warn asks the user, block denies, anything else is allowed silently.
    """
    try:
        output = hook_mod.run_hook(sys.stdin.read(), hook_client_factory)
    except Exception:
        hook_mod.log_exception(debug)
        output = None
    if output is not None:
        sys.stdout.write(json.dumps(output) + "\n")
    raise typer.Exit(0)
