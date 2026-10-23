import json

import pytest
from typer.testing import CliRunner

from slopsentry import cli, hook
from slopsentry.scoring import NamedResult, Report
from tests.conftest import (
    ESTABLISHED_LOOKALIKE,
    EXISTING,
    FRESH,
    FRESH_LOOKALIKE,
    MISSING,
    UNREACHABLE,
)

runner = CliRunner()


def event(command, tool="Bash"):
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}})


def run_hook(stdin, *args):
    return runner.invoke(cli.app, ["hook", *args], input=stdin)


def decision(result):
    """Exit 0 always; return the parsed decision, or None if the hook stayed silent."""
    assert result.exit_code == 0
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)["hookSpecificOutput"]


@pytest.fixture(autouse=True)
def no_swallowed_errors(fake_home):
    """The hook hides exceptions; fail any test that silently hit one."""
    yield
    log = fake_home / ".slopsentry" / "hook.log"
    if log.exists() and "expect_crash" not in log.read_text():
        pytest.fail(f"hook swallowed an exception:\n{log.read_text()}")


def _fixed_score(check):
    """Replace hook.score with one that runs a single fake check."""

    async def fake_score(package, client):
        status, detail, points = await check(package, client)
        return Report(package, [NamedResult("fake", status, detail, points)])

    return fake_score


@pytest.fixture
def client_calls(monkeypatch, make_client):
    calls = []

    def factory():
        calls.append(1)
        return make_client()

    monkeypatch.setattr(cli, "hook_client_factory", factory)
    return calls


@pytest.mark.parametrize(
    "command",
    [
        f"pip install {EXISTING}",
        f"pip3 install {EXISTING}",
        f"python -m pip install {EXISTING}",
        f"python3 -m pip install {EXISTING}",
        f"uv add {EXISTING}",
        f"uv pip install {EXISTING}",
        f"poetry add {EXISTING}",
        f"cd proj && pip install -U {EXISTING} typing_extensions; echo done",
    ],
)
def test_good_packages_allowed_silently(command, client_calls):
    assert decision(run_hook(event(command))) is None
    assert client_calls == [1]  # the packages really were checked


@pytest.mark.parametrize(
    "command",
    [
        f"pip install {MISSING}",
        f"pip3 install {MISSING}",
        f"python -m pip install {MISSING}",
        f"python3 -m pip install {MISSING}",
        f"uv add {MISSING}",
        f"uv pip install {MISSING}",
        f"poetry add {MISSING}",
        f"sudo pip install --no-cache-dir {MISSING}",
        f"git pull && pip install -e . -r reqs.txt {MISSING} | tail -1",
    ],
)
def test_missing_package_denied(command):
    out = decision(run_hook(event(command)))
    assert out["hookEventName"] == "PreToolUse"
    reason = out["permissionDecisionReason"]
    assert out["permissionDecision"] == "deny"
    assert f"{MISSING}: BLOCK, score 100 (exists: not found on PyPI)" in reason


def test_mixed_command_names_only_the_bad_package():
    out = decision(run_hook(event(f"pip install {EXISTING} {MISSING} typing-extensions")))
    reason = out["permissionDecisionReason"]
    assert out["permissionDecision"] == "deny"
    assert reason.startswith("SlopSentry blocked 1 of 3 packages:")
    assert f"- {MISSING}: BLOCK" in reason
    assert EXISTING not in reason


def test_warn_asks(monkeypatch):
    # A package scoring in the warn band (30-69): fresh, but with releases and links.
    async def warn_only(name, client):
        return ("warn", "first release 5 days ago", 40)

    monkeypatch.setattr(hook, "score", _fixed_score(warn_only))
    out = decision(run_hook(event("uv add newish-pkg")))
    reason = out["permissionDecisionReason"]
    assert out["permissionDecision"] == "ask"
    assert "SlopSentry flagged 1 of 1 packages:" in reason
    assert "newish-pkg: WARN, score 40 (fake: first release 5 days ago)" in reason


def test_block_wins_over_warn_across_chained_commands():
    out = decision(run_hook(event(f"pip install {FRESH} && poetry add {MISSING}")))
    assert out["permissionDecision"] == "deny"
    assert "blocked 2 of 2 packages" in out["permissionDecisionReason"]


def test_registry_error_allows_silently():
    assert decision(run_hook(event(f"pip install {UNREACHABLE}"))) is None


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "pip list",
        "pip uninstall requests",
        "npm install left-pad",
        "pip install -r requirements.txt",
        "pip install -e '.[dev]'",
        f"pip install --index-url https://my.index/simple {MISSING}",
        f"pip install --extra-index-url https://my.index/simple {MISSING}",
        'pip install "unterminated',
    ],
)
def test_nothing_to_check_exits_without_a_client(command, client_calls):
    assert decision(run_hook(event(command))) is None
    assert client_calls == []


@pytest.mark.parametrize(
    "stdin",
    [
        "{not json",
        "",
        "[]",
        json.dumps({"tool_name": "Bash"}),
        event(f"pip install {MISSING}", tool="Write"),
    ],
)
def test_malformed_or_non_bash_input_allowed(stdin, client_calls):
    assert decision(run_hook(stdin)) is None
    assert client_calls == []


def test_crash_in_scoring_exits_0_silently_and_logs(monkeypatch, fake_home):
    async def boom(package, client):
        raise RuntimeError("expect_crash: scoring exploded")

    monkeypatch.setattr(hook, "score", boom)
    result = run_hook(event(f"pip install {EXISTING}"))
    assert decision(result) is None
    assert result.stderr == ""

    log = (fake_home / ".slopsentry" / "hook.log").read_text()
    assert log.startswith("[20")  # ISO timestamp
    assert "RuntimeError: expect_crash: scoring exploded" in log
    assert "Traceback" in log


def test_debug_also_prints_the_crash_to_stderr(monkeypatch, fake_home):
    async def boom(package, client):
        raise RuntimeError("expect_crash: debug")

    monkeypatch.setattr(hook, "score", boom)
    result = run_hook(event(f"pip install {EXISTING}"), "--debug")
    assert decision(result) is None
    assert "RuntimeError: expect_crash: debug" in result.stderr
    assert (fake_home / ".slopsentry" / "hook.log").exists()


def test_unwritable_log_still_exits_0(monkeypatch, fake_home):
    async def boom(package, client):
        raise RuntimeError("expect_crash")

    (fake_home / ".slopsentry").write_text("a file where the log directory should be")
    monkeypatch.setattr(hook, "score", boom)
    assert decision(run_hook(event(f"pip install {EXISTING}"))) is None


def test_fresh_lookalike_denied_naming_the_real_package():
    out = decision(run_hook(event(f"pip install {FRESH_LOOKALIKE}")))
    assert out["permissionDecision"] == "deny"
    assert "lookalike: looks like requests" in out["permissionDecisionReason"]


def test_established_lookalike_allowed_silently():
    assert decision(run_hook(event(f"pip install {ESTABLISHED_LOOKALIKE}"))) is None
