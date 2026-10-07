"""Registry API clients (PyPI for now), with a per-client cache."""

import re
from typing import Any

import httpx

PYPI_URL = "https://pypi.org/pypi/{name}/json"


def normalize_name(name: str) -> str:
    """Normalise a PyPI project name per PEP 503: lowercase, runs of -_. become -."""
    return re.sub(r"[-_.]+", "-", name).lower()


class RegistryError(Exception):
    """The registry could not be reached or returned an unexpected response."""


class PyPIClient:
    def __init__(self, http: httpx.AsyncClient | None = None) -> None:
        self._http = http or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._cache: dict[str, dict[str, Any] | None] = {}
        # Errors are remembered too, so several checks don't each wait out the same outage.
        self._errors: dict[str, RegistryError] = {}

    async def get_project(self, name: str) -> dict[str, Any] | None:
        """Return the project's JSON metadata, or None if it does not exist."""
        key = normalize_name(name)
        if key in self._cache:
            return self._cache[key]
        if key in self._errors:
            raise self._errors[key]

        try:
            data = await self._fetch(key)
        except RegistryError as exc:
            self._errors[key] = exc
            raise
        self._cache[key] = data
        return data

    async def _fetch(self, key: str) -> dict[str, Any] | None:
        try:
            response = await self._http.get(PYPI_URL.format(name=key))
        except httpx.HTTPError as exc:
            raise RegistryError(f"could not reach PyPI: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RegistryError(f"PyPI returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RegistryError("PyPI returned a response that is not valid JSON") from exc
        if not isinstance(data, dict):
            raise RegistryError("PyPI returned an unexpected JSON shape")
        return data

    async def aclose(self) -> None:
        await self._http.aclose()
