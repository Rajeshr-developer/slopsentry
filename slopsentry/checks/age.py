"""Flag packages that look freshly registered: young, few releases, no project links."""

from datetime import datetime, timezone
from typing import Any

from slopsentry.checks import CheckResult
from slopsentry.registry import PyPIClient, RegistryError

NEW_PACKAGE_DAYS = 90
FEW_RELEASES = 2

NEW_POINTS = 40
FEW_RELEASES_POINTS = 20
NO_LINKS_POINTS = 20


def _parse_time(value: str) -> datetime:
    # Python 3.10's fromisoformat doesn't accept the "Z" suffix PyPI uses.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _upload_times(project: dict[str, Any]) -> list[datetime]:
    return [
        _parse_time(f["upload_time_iso_8601"])
        for files in (project.get("releases") or {}).values()
        for f in files
        if f.get("upload_time_iso_8601")
    ]


def _has_links(info: dict[str, Any]) -> bool:
    return bool(info.get("home_page")) or any((info.get("project_urls") or {}).values())


async def check_age(name: str, client: PyPIClient, now: datetime | None = None) -> CheckResult:
    try:
        project = await client.get_project(name)
    except RegistryError as exc:
        return ("error", str(exc), 0)
    if project is None:
        return ("skip", "not found on PyPI", 0)
    # PyPI has deprecated `releases` in this endpoint. Absent means unknown, not new.
    if "releases" not in project:
        return ("skip", "release history unavailable", 0)

    now = now or datetime.now(timezone.utc)
    findings: list[str] = []
    points = 0

    uploads = _upload_times(project)
    if not uploads:
        findings.append("no released files")
        points += NEW_POINTS
    else:
        age_days = (now - min(uploads)).days
        if age_days < NEW_PACKAGE_DAYS:
            findings.append(f"first release {age_days} days ago")
            points += NEW_POINTS

    releases = sum(1 for files in (project.get("releases") or {}).values() if files)
    if releases <= FEW_RELEASES:
        findings.append(f"only {releases} release{'s' if releases != 1 else ''}")
        points += FEW_RELEASES_POINTS

    if not _has_links(project.get("info") or {}):
        findings.append("no homepage or repository link")
        points += NO_LINKS_POINTS

    if findings:
        return ("warn", "; ".join(findings), points)
    first = min(uploads).date().isoformat()
    return ("pass", f"first released {first}, {releases} releases, has project links", 0)
