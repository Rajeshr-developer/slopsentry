import asyncio

import pytest

from slopsentry.checks.lookalike import (
    ESTABLISHED_LOOKALIKE_POINTS,
    LOOKALIKE_POINTS,
    bundled_index,
    check_lookalike,
    edit_distance,
    find_lookalike,
    popular_index,
)
from slopsentry.registry import normalize_name
from tests.conftest import (
    ESTABLISHED_LOOKALIKE,
    FRESH_LOOKALIKE,
    MISSING,
    UNREACHABLE,
)

# Offline fixture: a small "popular" list, most downloaded first.
POPULAR = popular_index(
    [
        "requests",
        "numpy",
        "pandas",
        "python-docx",
        "djangorestframework",
        "six",
        "mypy-boto3-ec2",
        "google-cloud-storage",
    ]
)

FLAGGED = [
    ("reqeusts", "requests"),  # transposition
    ("requets", "requests"),  # deletion
    ("python-requests", "requests"),  # added prefix
    ("numpyy", "numpy"),  # insertion
    ("pandas-py", "pandas"),  # added suffix
]
CLEAN = ["requests", "numpy", "zqxv-ledger-toolkit"]


@pytest.mark.parametrize(("name", "target"), FLAGGED)
def test_lookalikes_flag(name, target):
    assert find_lookalike(name, POPULAR) == target


@pytest.mark.parametrize(("name", "target"), FLAGGED)
def test_lookalikes_flag_against_bundled_list(name, target):
    assert find_lookalike(name, bundled_index()) == target


@pytest.mark.parametrize("name", CLEAN)
def test_clean_names_pass(name, make_client):
    result = asyncio.run(_check(name, make_client(), POPULAR))
    assert result[0] in ("pass", "skip")
    assert result[2] == 0


@pytest.mark.parametrize("name", ["requests", "Requests", "numpy"])
def test_popular_package_is_skipped(name, make_client):
    # Popular names never flag each other (request vs requests is about the unknown name).
    assert asyncio.run(_check(name, make_client(), POPULAR)) == ("skip", "popular package", 0)


@pytest.mark.parametrize(
    ("name", "target"),
    [
        ("django-rest-framework", "djangorestframework"),  # separators only
        ("djangorest_framework", "djangorestframework"),
        ("docx", "python-docx"),  # removed prefix
        ("pandas-lib", "pandas"),
        ("py-numpy", "numpy"),
        ("numpy-python", "numpy"),
    ],
)
def test_separator_and_affix_rules(name, target):
    assert find_lookalike(name, POPULAR) == target


def test_long_names_allow_distance_two():
    assert find_lookalike("gogle-cloud-storag", POPULAR) == "google-cloud-storage"


def test_short_names_allow_only_distance_one():
    assert find_lookalike("nunpyy", POPULAR) is None  # distance 2, 6 characters


def test_guard_1_no_edit_matching_under_five_characters():
    assert find_lookalike("sax", POPULAR) is None  # one edit from six
    assert find_lookalike("sixx", POPULAR) is None


def test_guard_2_family_member_differing_in_one_segment():
    # Distance 2 and only the last segment differs: a sibling, not a typo.
    assert find_lookalike("mypy-boto3-emr", POPULAR) is None
    # A distance-1 typo inside the family still flags.
    assert find_lookalike("mypy-boto3-ec22", POPULAR) == "mypy-boto3-ec2"


def test_closest_match_wins_then_most_popular():
    index = popular_index(["abcdef", "abcdeg", "abcdefgh"])
    assert find_lookalike("abcdex", index) == "abcdef"  # tie at distance 1: higher rank
    index = popular_index(["xbcdefg", "abcdefg"])
    assert find_lookalike("abcdefg-py", index) == "abcdefg"  # affix beats a worse edit


@pytest.mark.parametrize(
    ("a", "b", "limit", "expected"),
    [
        ("requests", "requests", 1, 0),
        ("reqeusts", "requests", 1, 1),
        ("requets", "requests", 1, 1),
        ("rqeuests", "requests", 2, 1),
        ("abc", "xyz", 2, 3),  # over the limit reports limit + 1
        ("short", "much-longer", 1, 2),
    ],
)
def test_edit_distance(a, b, limit, expected):
    assert edit_distance(a, b, limit) == expected


def test_bundled_list_is_normalised_and_unique():
    names = bundled_index().names
    assert len(names) == 5000
    assert len(set(names)) == 5000
    assert all(normalize_name(n) == n for n in names)
    assert {"requests", "numpy", "pandas"} <= set(names)


def test_established_lookalike_scores_15(make_client):
    result = asyncio.run(_check(ESTABLISHED_LOOKALIKE, make_client(), POPULAR))
    assert result == (
        "warn",
        "looks like requests (established package)",
        ESTABLISHED_LOOKALIKE_POINTS,
    )
    assert ESTABLISHED_LOOKALIKE_POINTS == 15


@pytest.mark.parametrize("name", [FRESH_LOOKALIKE, MISSING, UNREACHABLE])
def test_new_missing_or_unverified_lookalike_scores_50(make_client, name):
    # Fresh (age warns), not on PyPI (age skips) or registry down (age errors): not established.
    index = popular_index(["requests", "reqeusts-pr", "flaky-pkgs"])
    status, detail, points = asyncio.run(_check(name, make_client(), index))
    assert status == "warn"
    assert detail.startswith("looks like ")
    assert "established" not in detail
    assert points == LOOKALIKE_POINTS == 50


async def _check(name, client, index):
    try:
        return await check_lookalike(name, client, index)
    finally:
        await client.aclose()
