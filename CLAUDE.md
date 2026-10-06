# SlopSentry
CLI that checks packages for slopsquatting (AI-hallucinated or
malicious lookalike packages) before they are installed.

## Stack
Python 3.12, Typer (CLI), httpx (async registry calls),
rich (--explain output), pytest, ruff

## Structure
- slopsentry/checks/   one file per check; each returns (status, detail, points)
- slopsentry/registry.py   PyPI and npm API clients, cached
- slopsentry/cli.py   commands: check, install, hook
- tests/   pytest, registry responses always mocked

## Rules
- Tests must run offline: mock every registry call
- Never install real packages during tests
- Run `pytest` and `ruff check` before finishing any task
- Keep each change small; explain what changed at the end