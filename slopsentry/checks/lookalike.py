"""Flag names that look like a popular PyPI package: typos, separators and affixes."""

import json
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files

from slopsentry.checks import CheckResult
from slopsentry.checks.age import check_age
from slopsentry.registry import PyPIClient, normalize_name

LOOKALIKE_POINTS = 50
# An established package (age check passes cleanly) that resembles a popular one is most
# likely a legitimate neighbour, e.g. simpy/sympy: shown, but not enough to warn alone.
ESTABLISHED_LOOKALIKE_POINTS = 15

# Edit distance allowed: 1, or 2 for names longer than LONG_NAME characters.
LONG_NAME = 10
# Guard 1: names shorter than this get no edit-distance matching (od/id, sax/six).
MIN_EDIT_LENGTH = 5

PREFIXES = ("py-", "python-")
SUFFIXES = ("-py", "-python", "-lib")


@dataclass(frozen=True)
class PopularIndex:
    names: tuple[str, ...]  # normalised, most downloaded first
    rank: dict[str, int] = field(init=False)
    squashed: dict[str, list[str]] = field(init=False)

    def __post_init__(self) -> None:
        rank = {name: i for i, name in enumerate(self.names)}
        squashed: dict[str, list[str]] = {}
        for name in self.names:
            squashed.setdefault(name.replace("-", ""), []).append(name)
        object.__setattr__(self, "rank", rank)
        object.__setattr__(self, "squashed", squashed)


def popular_index(names: list[str]) -> PopularIndex:
    return PopularIndex(tuple(normalize_name(n) for n in names))


@cache
def bundled_index() -> PopularIndex:
    data = files("slopsentry.data").joinpath("top_pypi.json").read_text(encoding="utf-8")
    return PopularIndex(tuple(json.loads(data)["packages"]))


def edit_distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein (optimal string alignment) distance, or limit + 1 if over limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    before: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], before[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        before, prev = prev, cur
    return prev[-1]


def _one_segment_differs(a: str, b: str) -> bool:
    """Guard 2: family members like mypy-boto3-emr and mypy-boto3-ec2."""
    sa, sb = a.split("-"), b.split("-")
    return len(sa) == len(sb) > 1 and sum(x != y for x, y in zip(sa, sb, strict=True)) == 1


def _affix_variants(name: str) -> set[str]:
    """Names reachable by removing or adding one common affix."""
    variants = {name[len(p) :] for p in PREFIXES if name.startswith(p)}
    variants |= {name[: -len(s)] for s in SUFFIXES if name.endswith(s)}
    variants |= {p + name for p in PREFIXES} | {name + s for s in SUFFIXES}
    return {v for v in variants if v and v != name}


def find_lookalike(name: str, index: PopularIndex) -> str | None:
    """Return the popular package NAME most resembles, or None. NAME must not be popular."""
    name = normalize_name(name)
    # (distance, rank, target): separator and affix matches count as distance 0.
    matches: list[tuple[int, int, str]] = []

    for target in index.squashed.get(name.replace("-", ""), []):
        if target != name:
            matches.append((0, index.rank[target], target))
    for target in _affix_variants(name):
        if target in index.rank:
            matches.append((0, index.rank[target], target))

    if len(name) >= MIN_EDIT_LENGTH:
        limit = 2 if len(name) > LONG_NAME else 1
        for target in index.names:
            if abs(len(target) - len(name)) > limit:
                continue
            distance = edit_distance(name, target, limit)
            if distance > limit:
                continue
            if distance == 2 and _one_segment_differs(name, target):
                continue
            matches.append((distance, index.rank[target], target))

    return min(matches)[2] if matches else None


async def check_lookalike(
    name: str, client: PyPIClient, index: PopularIndex | None = None
) -> CheckResult:
    index = index or bundled_index()
    if normalize_name(name) in index.rank:
        return ("skip", "popular package", 0)

    target = find_lookalike(name, index)
    if target is None:
        return ("pass", "no close match among popular packages", 0)

    # Reuses the cached registry response, so this costs no extra request.
    age_status, _, _ = await check_age(name, client)
    if age_status == "pass":
        return ("warn", f"looks like {target} (established package)", ESTABLISHED_LOOKALIKE_POINTS)
    return ("warn", f"looks like {target}", LOOKALIKE_POINTS)
