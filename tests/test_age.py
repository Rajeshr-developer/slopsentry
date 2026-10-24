import asyncio
from datetime import datetime, timezone

from slopsentry.checks.age import check_age
from tests.conftest import EXISTING, FRESH, MISSING, NO_HISTORY, UNREACHABLE


def run(name, client, now=None):
    async def go():
        try:
            return await check_age(name, client, now=now)
        finally:
            await client.aclose()

    return asyncio.run(go())


def test_established_package_passes(make_client):
    status, detail, points = run(EXISTING, make_client())
    assert status == "pass"
    assert "first released 2015-03-01" in detail
    assert points == 0


def test_fresh_package_warns_on_every_signal(make_client):
    status, detail, points = run(FRESH, make_client())
    assert status == "warn"
    assert "first release 5 days ago" in detail
    assert "only 1 release" in detail
    assert "no homepage or repository link" in detail
    assert points == 80


def test_age_threshold_uses_now(make_client):
    # Shortly after its first release, an established package also counts as new.
    now = datetime(2015, 3, 31, 12, tzinfo=timezone.utc)
    status, detail, points = run(EXISTING, make_client(), now=now)
    assert status == "warn"
    assert detail == "first release 30 days ago"
    assert points == 40


def test_missing_package_is_skipped(make_client):
    assert run(MISSING, make_client()) == ("skip", "not found on PyPI", 0)


def test_unreachable_registry_is_error(make_client):
    assert run(UNREACHABLE, make_client())[0] == "error"


def test_missing_release_history_is_neutral(make_client):
    assert run(NO_HISTORY, make_client()) == ("skip", "release history unavailable", 0)
