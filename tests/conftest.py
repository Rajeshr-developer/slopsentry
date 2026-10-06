from datetime import UTC, datetime, timedelta

import httpx
import pytest

from slopsentry import cli
from slopsentry.registry import PyPIClient

EXISTING = "requests"
MISSING = "reqeusts-pro"
UNREACHABLE = "flaky-pkg"
FRESH = "fresh-pkg"


def established(name: str) -> dict:
    """An old, actively released package with a repository link."""
    return {
        "info": {"name": name, "project_urls": {"Source": f"https://github.com/example/{name}"}},
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2015-03-01T12:00:00.000000Z"}],
            "1.1.0": [{"upload_time_iso_8601": "2018-06-01T12:00:00.000000Z"}],
            "2.0.0": [{"upload_time_iso_8601": "2024-05-29T15:37:47.000000Z"}],
        },
    }


def fresh(name: str) -> dict:
    """Registered days ago: one release, no links. Dated relative to now."""
    uploaded = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    return {
        "info": {"name": name, "home_page": "", "project_urls": None},
        "releases": {"0.0.1": [{"upload_time_iso_8601": uploaded}]},
    }


# Mocked PyPI only knows normalised names, so un-normalised lookups would 404.
KNOWN = {"requests": established, "typing-extensions": established, FRESH: fresh}


def pypi_handler(request: httpx.Request) -> httpx.Response:
    name = request.url.path.removeprefix("/pypi/").removesuffix("/json")
    if name in KNOWN:
        return httpx.Response(200, json=KNOWN[name](name))
    if name == MISSING:
        return httpx.Response(404, json={"message": "Not Found"})
    if name == UNREACHABLE:
        raise httpx.ConnectError("connection refused", request=request)
    raise AssertionError(f"unmocked request: {request.url}")


@pytest.fixture
def make_client():
    def factory() -> PyPIClient:
        return PyPIClient(httpx.AsyncClient(transport=httpx.MockTransport(pypi_handler)))

    return factory


@pytest.fixture(autouse=True)
def no_network(monkeypatch, make_client):
    """Route the CLI through the mock and fail loudly on any real HTTP call."""

    def blocked(*args, **kwargs):
        raise AssertionError("real network access attempted in tests")

    monkeypatch.setattr(cli, "client_factory", make_client)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
