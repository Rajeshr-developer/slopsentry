import httpx
import pytest

from slopsentry import cli
from slopsentry.registry import PyPIClient

EXISTING = "requests"
MISSING = "reqeusts-pro"
UNREACHABLE = "flaky-pkg"

# Mocked PyPI only knows normalised names, so un-normalised lookups would 404.
KNOWN = {"requests", "typing-extensions"}


def pypi_handler(request: httpx.Request) -> httpx.Response:
    name = request.url.path.removeprefix("/pypi/").removesuffix("/json")
    if name in KNOWN:
        return httpx.Response(200, json={"info": {"name": name}})
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
