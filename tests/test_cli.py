from typer.testing import CliRunner

from slopsentry.cli import app
from tests.conftest import EXISTING, FRESH, MISSING, UNREACHABLE

runner = CliRunner()


def test_check_existing_package():
    result = runner.invoke(app, ["check", EXISTING])
    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "found on PyPI" in result.output


def test_check_missing_package():
    result = runner.invoke(app, ["check", MISSING])
    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "not found on PyPI" in result.output


def test_unreachable_registry_warns_by_default():
    result = runner.invoke(app, ["check", UNREACHABLE])
    assert result.exit_code == 0
    assert "WARN" in result.output


def test_unreachable_registry_blocks_with_strict():
    result = runner.invoke(app, ["check", "--strict", UNREACHABLE])
    assert result.exit_code == 2
    assert "ERROR" in result.output


def test_fresh_package_warns_without_failing():
    result = runner.invoke(app, ["check", FRESH])
    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "WARN" in result.output
    assert "first release 5 days ago" in result.output
