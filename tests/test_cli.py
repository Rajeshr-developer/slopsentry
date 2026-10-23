import pytest
from typer.testing import CliRunner

from slopsentry import cli, scoring
from slopsentry.cli import app
from tests.conftest import (
    ESTABLISHED_LOOKALIKE,
    EXISTING,
    FRESH,
    FRESH_LOOKALIKE,
    GARBLED,
    MISSING,
    UNREACHABLE,
)

# Wide enough that rich doesn't wrap the lines under test.
runner = CliRunner(env={"COLUMNS": "200"})


def test_check_existing_package():
    result = runner.invoke(app, ["check", EXISTING])
    assert result.exit_code == 0
    assert "PASS requests: score 0" in result.output
    assert "  - " not in result.output  # no reasons for a pass


def test_check_missing_package_blocks():
    result = runner.invoke(app, ["check", MISSING])
    assert result.exit_code == 1
    assert "BLOCK" in result.output
    assert "exists: not found on PyPI (+100)" in result.output


def test_unreachable_registry_warns_by_default():
    result = runner.invoke(app, ["check", UNREACHABLE])
    assert result.exit_code == 0
    assert "WARN" in result.output
    assert "use --strict to block" in result.output
    # exists and age both hit the same outage; the reason is shown once.
    assert result.output.count("could not reach PyPI") == 1


def test_unreachable_registry_errors_with_strict():
    result = runner.invoke(app, ["check", "--strict", UNREACHABLE])
    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert "could not be verified (--strict)" in result.output


def test_strict_has_no_effect_when_registry_is_reachable():
    result = runner.invoke(app, ["check", "--strict", EXISTING])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_fresh_package_blocks_with_reasons():
    result = runner.invoke(app, ["check", FRESH])
    assert result.exit_code == 1
    assert "BLOCK fresh-pkg: score 80" in result.output
    assert "first release 5 days ago" in result.output


def test_explain_prints_table_total_and_verdict():
    result = runner.invoke(app, ["check", "--explain", FRESH])
    assert result.exit_code == 1
    for text in ("Check", "Status", "Detail", "Points", "exists", "age", "pass", "warn"):
        assert text in result.output
    assert "Total: 80 points (warn at 30, block at 70)" in result.output
    assert "BLOCK fresh-pkg: score 80" in result.output
    assert "  - " not in result.output  # the table replaces the reasons list


@pytest.mark.parametrize("spec", ["requests==2.31.0", "requests[socks]", "Requests[socks]>=2"])
def test_requirement_specs_resolve_to_name(spec):
    result = runner.invoke(app, ["check", spec])
    assert result.exit_code == 0
    assert "PASS" in result.output


@pytest.mark.parametrize(
    ("spec", "message"),
    [("", "package name is empty"), ("requests[socks", "invalid package spec")],
)
def test_invalid_spec_exits_2_without_request(monkeypatch, spec, message):
    def no_client():
        raise AssertionError("registry client created for invalid input")

    monkeypatch.setattr(cli, "client_factory", no_client)
    result = runner.invoke(app, ["check", spec])
    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert message in result.output


def test_non_json_response_warns_by_default():
    result = runner.invoke(app, ["check", GARBLED])
    assert result.exit_code == 0
    assert "WARN" in result.output
    assert "not valid JSON" in result.output


def fixed_points(points):
    async def check(name, client):
        return ("warn", f"synthetic {points}", points)

    return check


@pytest.mark.parametrize(
    ("points", "label", "exit_code"),
    [(29, "PASS", 0), (30, "WARN", 0), (69, "WARN", 0), (70, "BLOCK", 1)],
)
def test_verdict_boundaries_through_cli(monkeypatch, points, label, exit_code):
    monkeypatch.setattr(scoring, "ALL_CHECKS", [("fake", fixed_points(points))])
    result = runner.invoke(app, ["check", EXISTING])
    assert result.exit_code == exit_code
    assert f"{label} requests: score {points}" in result.output


def test_established_lookalike_scores_15_and_passes():
    result = runner.invoke(app, ["check", ESTABLISHED_LOOKALIKE])
    assert result.exit_code == 0
    assert "PASS reqeusts: score 15" in result.output

    explained = runner.invoke(app, ["check", "--explain", ESTABLISHED_LOOKALIKE])
    assert explained.exit_code == 0
    assert "looks like requests (established package)" in explained.output
    assert "15" in explained.output


def test_lookalike_released_5_days_ago_blocks():
    result = runner.invoke(app, ["check", FRESH_LOOKALIKE])
    assert result.exit_code == 1
    # exists 0 + age 80 (new, 1 release, no links) + lookalike 50
    assert "BLOCK requets: score 130" in result.output
    assert "lookalike: looks like requests (+50)" in result.output
