"""Claude Code PreToolUse hook: check the packages in Bash install commands.

The hook fails open. Anything it can't parse, a registry outage or a crash allows the
command; only a scored warn or block produces output.
"""

import asyncio
import json
import os
import re
import shlex
import sys
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from slopsentry.registry import PyPIClient, normalize_name
from slopsentry.scoring import Report, score, verdict_for
from slopsentry.spec import InvalidPackageSpec, parse_package_name

HOOK_TIMEOUT = 5.0

SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "\n"}
# Characters shlex would otherwise split words on, which appear in URLs and specs.
EXTRA_WORDCHARS = ":@%+,^![]{}$#"

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PIP = re.compile(r"^pip(3(\.\d+)?)?$")
PYTHON = re.compile(r"^python(3(\.\d+)?)?$")

# Options that take a value, per tool. Their values are never package names.
PIP_VALUE_OPTS = {
    "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-t", "--target",
    "--platform", "--python-version", "--implementation", "--abi", "--root", "--prefix",
    "--src", "--upgrade-strategy", "-C", "--config-settings", "--global-option",
    "--no-binary", "--only-binary", "--progress-bar", "--root-user-action", "--report",
    "--group", "-i", "--index-url", "--extra-index-url", "-f", "--find-links", "--log",
    "--proxy", "--retries", "--timeout", "--exists-action", "--trusted-host", "--cert",
    "--client-cert", "--cache-dir", "--python", "--keyring-provider", "--use-feature",
    "--use-deprecated", "--resume-retries",
}  # fmt: skip
UV_VALUE_OPTS = {
    "-r", "--requirements", "--requirement", "-e", "--editable", "-c", "--constraints",
    "--constraint", "--overrides", "-b", "--build-constraints", "--group", "--optional",
    "--extra", "--tag", "--branch", "--rev", "-m", "--marker", "--index", "--default-index",
    "-i", "--index-url", "--extra-index-url", "-f", "--find-links", "-p", "--python",
    "--python-version", "--python-platform", "-t", "--target", "--prefix", "--package",
    "--script", "--directory", "--project", "--config-file", "--cache-dir", "-P",
    "--upgrade-package", "--reinstall-package", "--no-binary-package", "--no-build-package",
    "--index-strategy", "--keyring-provider", "--resolution", "--prerelease",
    "--exclude-newer", "--link-mode", "--color", "--refresh-package", "--bounds", "-C",
    "--config-setting", "--allow-insecure-host",
}  # fmt: skip
POETRY_VALUE_OPTS = {
    "-G", "--group", "-E", "--extras", "--source", "--python", "--platform", "--markers",
    "-C", "--directory", "-P", "--project",
}  # fmt: skip

# A custom index means packages may legitimately be missing from PyPI: skip the command.
PIP_INDEX_OPTS = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links"}
UV_INDEX_OPTS = PIP_INDEX_OPTS | {"--index", "--default-index"}
POETRY_INDEX_OPTS = {"--source"}

SUDO_VALUE_OPTS = {"-u", "-g", "-C", "-D", "-p", "-U", "-r", "-t", "-T"}
ENV_VALUE_OPTS = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}

ARCHIVE_SUFFIXES = (".whl", ".tar.gz", ".tgz", ".tar.bz2", ".zip")

ClientFactory = Callable[[], PyPIClient]


def read_event(raw: str) -> str | None:
    """Return the Bash command from a PreToolUse event, or None for anything else."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) else None


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.wordchars += EXTRA_WORDCHARS
    # shlex ends a word at `#`; bash only starts a comment at the start of a word.
    lexer.commenters = ""
    lexer.whitespace = " \t\r"  # newline separates commands, so keep it as a token
    return list(lexer)


def _segments(tokens: list[str]) -> list[list[str]]:
    """Split tokens into simple commands, dropping redirections and their targets."""
    segments: list[list[str]] = [[]]
    skip_next = in_comment = False
    for tok in tokens:
        if in_comment:
            in_comment = tok != "\n"
            if not in_comment:
                segments.append([])
        elif skip_next:
            skip_next = False
        elif tok.startswith("#"):
            in_comment = True
        elif tok in SEPARATORS:
            segments.append([])
        elif set(tok) <= set("<>&"):
            # Redirection like `> log` or `2>&1`: drop its target and any fd number before it.
            skip_next = True
            if segments[-1] and segments[-1][-1].isdigit():
                segments[-1].pop()
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _strip_prefixes(words: list[str]) -> list[str]:
    """Drop leading VAR=value assignments, `env` and `sudo` (with their options)."""
    i = 0
    while i < len(words):
        word = words[i]
        if ASSIGNMENT.match(word):
            i += 1
        elif word in ("sudo", "env"):
            value_opts = SUDO_VALUE_OPTS if word == "sudo" else ENV_VALUE_OPTS
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in value_opts else 1
        else:
            break
    return words[i:]


def _skip_options(words: list[str], value_opts: set[str]) -> list[str]:
    """Drop leading options so the subcommand comes first."""
    i = 0
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in value_opts else 1
    return words[i:]


def _install_args(words: list[str]) -> tuple[list[str], set[str], set[str], bool] | None:
    """If WORDS is a supported install command, return (args, value opts, index opts, poetry)."""
    if not words:
        return None
    program = os.path.basename(words[0])
    rest = words[1:]

    if PYTHON.match(program):
        if rest[:2] != ["-m", "pip"]:
            return None
        program, rest = "pip", rest[2:]

    if PIP.match(program):
        rest = _skip_options(rest, PIP_VALUE_OPTS)
        if rest[:1] == ["install"]:
            return rest[1:], PIP_VALUE_OPTS, PIP_INDEX_OPTS, False
    elif program == "uv":
        rest = _skip_options(rest, UV_VALUE_OPTS)
        if rest[:1] == ["add"]:
            return rest[1:], UV_VALUE_OPTS, UV_INDEX_OPTS, False
        if rest[:2] == ["pip", "install"]:
            return rest[2:], UV_VALUE_OPTS, UV_INDEX_OPTS, False
    elif program == "poetry":
        rest = _skip_options(rest, POETRY_VALUE_OPTS)
        if rest[:1] == ["add"]:
            return rest[1:], POETRY_VALUE_OPTS, POETRY_INDEX_OPTS, True
    return None


def _uses_custom_index(args: list[str], index_opts: set[str]) -> bool:
    for arg in args:
        if arg.split("=", 1)[0] in index_opts:
            return True
        # Attached short form, e.g. -ihttps://example.com/simple
        if not arg.startswith("--") and len(arg) > 2 and arg[:2] in index_opts:
            return True
    return False


def _is_local_or_url(arg: str) -> bool:
    return (
        arg.startswith((".", "/", "~", "git+", "file:"))
        or "/" in arg
        or "\\" in arg
        or "://" in arg
        or arg.endswith(ARCHIVE_SUFFIXES)
    )


def _package_names(args: list[str], value_opts: set[str], poetry: bool) -> list[str]:
    names = []
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg.startswith("-"):
            if arg in value_opts:
                i += 1  # skip the option's value (-r file, -e path, --group dev, ...)
            continue
        if i < len(args) and args[i] == "@":
            i += 2  # `pkg @ url` direct reference: installed from the URL, not PyPI
            continue
        if _is_local_or_url(arg):
            continue
        if "@" in arg:
            if not poetry:
                continue  # PEP 508 `pkg@url` direct reference
            arg = arg.split("@", 1)[0]  # poetry's `pkg@^1.0` version constraint
        try:
            names.append(parse_package_name(arg))
        except InvalidPackageSpec:
            continue
    return names


def extract_packages(command: str) -> list[str]:
    """Return the PyPI package names that COMMAND would install, de-duplicated in order."""
    try:
        tokens = _tokenize(command)
    except ValueError:
        return []  # unbalanced quotes and the like: can't tell, so allow

    names: dict[str, str] = {}
    for segment in _segments(tokens):
        found = _install_args(_strip_prefixes(segment))
        if found is None:
            continue
        args, value_opts, index_opts, poetry = found
        if _uses_custom_index(args, index_opts):
            continue
        for name in _package_names(args, value_opts, poetry):
            names.setdefault(normalize_name(name), name)
    return list(names.values())


async def _score_all(packages: list[str], client_factory: ClientFactory) -> list[Report]:
    client = client_factory()
    try:
        return list(await asyncio.gather(*(score(p, client) for p in packages)))
    finally:
        await client.aclose()


def _describe(report: Report) -> str:
    verdict = verdict_for(report.total)
    reasons = "; ".join(f"{r.check}: {r.detail}" for r in report.reasons if r.status != "error")
    return f"- {report.package}: {verdict.upper()}, score {report.total} ({reasons})"


def decide(reports: list[Report]) -> dict[str, Any] | None:
    """Turn reports into Claude Code hook output, or None to allow silently.

    Registry errors score 0 points, so an unverifiable package is allowed here.
    """
    verdicts = [verdict_for(r.total) for r in reports]
    flagged = [r for r, v in zip(reports, verdicts, strict=True) if v != "pass"]
    if not flagged:
        return None

    decision = "deny" if "block" in verdicts else "ask"
    action = "blocked" if decision == "deny" else "flagged"
    lines = [f"SlopSentry {action} {len(flagged)} of {len(reports)} packages:"]
    lines += [_describe(r) for r in flagged]
    if decision == "deny":
        lines.append(
            "These may be hallucinated or lookalike packages. Check the names; "
            "if one is intended, ask the user to confirm and install it themselves."
        )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "\n".join(lines),
        }
    }


def run_hook(raw: str, client_factory: ClientFactory) -> dict[str, Any] | None:
    command = read_event(raw)
    if command is None:
        return None
    packages = extract_packages(command)
    if not packages:
        return None  # nothing to check: no registry client is created
    return decide(asyncio.run(_score_all(packages, client_factory)))


def log_path() -> Path:
    return Path.home() / ".slopsentry" / "hook.log"


def log_exception(debug: bool) -> None:
    """Record the exception being handled. Never raises: the hook must still allow."""
    entry = f"[{datetime.now(UTC).isoformat()}] {traceback.format_exc()}"
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(entry)
    except OSError:
        pass
    if debug:
        sys.stderr.write(entry)
