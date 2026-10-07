"""Run every check, total the points, and turn the total into a verdict."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from slopsentry.checks import CheckResult
from slopsentry.checks.age import check_age
from slopsentry.checks.exists import check_exists
from slopsentry.registry import PyPIClient

# Verdict thresholds. Tune here: total < WARN_AT passes, total >= BLOCK_AT blocks.
WARN_AT = 30
BLOCK_AT = 70

Check = Callable[[str, PyPIClient], Awaitable[CheckResult]]

ALL_CHECKS: list[tuple[str, Check]] = [
    ("exists", check_exists),
    ("age", check_age),
]

REASON_STATUSES = ("warn", "fail", "error")


def verdict_for(total: int) -> str:
    if total >= BLOCK_AT:
        return "block"
    if total >= WARN_AT:
        return "warn"
    return "pass"


@dataclass(frozen=True)
class NamedResult:
    check: str
    status: str
    detail: str
    points: int


@dataclass(frozen=True)
class Report:
    package: str
    results: list[NamedResult]

    @property
    def total(self) -> int:
        return sum(r.points for r in self.results)

    @property
    def has_errors(self) -> bool:
        return any(r.status == "error" for r in self.results)

    @property
    def verdict(self) -> str:
        verdict = verdict_for(self.total)
        # An unverified package must not read as a pass.
        if verdict == "pass" and self.has_errors:
            return "warn"
        return verdict

    @property
    def reasons(self) -> list[NamedResult]:
        """Results worth showing the user, with repeated details (e.g. one outage) collapsed."""
        seen: set[str] = set()
        reasons = []
        for r in self.results:
            if r.status in REASON_STATUSES and r.detail not in seen:
                seen.add(r.detail)
                reasons.append(r)
        return reasons


async def score(package: str, client: PyPIClient) -> Report:
    results = []
    for name, check in ALL_CHECKS:
        status, detail, points = await check(package, client)
        results.append(NamedResult(name, status, detail, points))
    return Report(package, results)
