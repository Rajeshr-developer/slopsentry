import asyncio

from slopsentry.checks.exists import MISSING_POINTS, check_exists
from tests.conftest import EXISTING, MISSING, UNREACHABLE


def run(name, client):
    async def go():
        try:
            return await check_exists(name, client)
        finally:
            await client.aclose()

    return asyncio.run(go())


def test_existing_package_passes(make_client):
    assert run(EXISTING, make_client()) == ("pass", "found on PyPI", 0)


def test_missing_package_fails(make_client):
    assert run(MISSING, make_client()) == ("fail", "not found on PyPI", MISSING_POINTS)


def test_unreachable_registry_is_error(make_client):
    status, detail, points = run(UNREACHABLE, make_client())
    assert status == "error"
    assert "could not reach PyPI" in detail
    assert points == 0
