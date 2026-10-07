import asyncio

import pytest

from slopsentry import scoring
from slopsentry.scoring import BLOCK_AT, WARN_AT, NamedResult, Report, score, verdict_for
from tests.conftest import EXISTING, FRESH, MISSING, UNREACHABLE


def test_thresholds():
    assert (WARN_AT, BLOCK_AT) == (30, 70)


@pytest.mark.parametrize(
    ("total", "expected"),
    [(0, "pass"), (29, "pass"), (30, "warn"), (69, "warn"), (70, "block"), (180, "block")],
)
def test_verdict_boundaries(total, expected):
    assert verdict_for(total) == expected


def result(status, detail, points, check="c"):
    return NamedResult(check, status, detail, points)


def test_total_sums_points():
    report = Report("x", [result("warn", "a", 20), result("fail", "b", 15)])
    assert report.total == 35
    assert report.verdict == "warn"


def test_errors_never_read_as_pass():
    report = Report("x", [result("error", "could not reach PyPI", 0)])
    assert report.total == 0
    assert report.verdict == "warn"


def test_errors_dont_lower_a_block():
    report = Report("x", [result("fail", "bad", 100), result("error", "outage", 0)])
    assert report.verdict == "block"


def test_reasons_skip_pass_and_skip_and_collapse_duplicates():
    report = Report(
        "x",
        [
            result("pass", "fine", 0, "a"),
            result("skip", "unknown", 0, "b"),
            result("error", "outage", 0, "c"),
            result("error", "outage", 0, "d"),
            result("warn", "young", 40, "e"),
        ],
    )
    assert [(r.check, r.detail) for r in report.reasons] == [("c", "outage"), ("e", "young")]


def run_score(name, client):
    async def go():
        try:
            return await score(name, client)
        finally:
            await client.aclose()

    return asyncio.run(go())


@pytest.mark.parametrize(
    ("name", "total", "verdict"),
    [
        (EXISTING, 0, "pass"),
        (FRESH, 80, "block"),
        (MISSING, 100, "block"),
        (UNREACHABLE, 0, "warn"),
    ],
)
def test_score_runs_all_checks(make_client, name, total, verdict):
    report = run_score(name, make_client())
    assert [r.check for r in report.results] == [c for c, _ in scoring.ALL_CHECKS]
    assert (report.total, report.verdict) == (total, verdict)
