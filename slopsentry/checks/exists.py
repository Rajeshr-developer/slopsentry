"""Check that a package exists on PyPI."""

from slopsentry.checks import CheckResult
from slopsentry.registry import PyPIClient, RegistryError

MISSING_POINTS = 100


async def check_exists(name: str, client: PyPIClient) -> CheckResult:
    try:
        project = await client.get_project(name)
    except RegistryError as exc:
        return ("error", str(exc), 0)

    if project is None:
        return ("fail", "not found on PyPI", MISSING_POINTS)
    return ("pass", "found on PyPI", 0)
