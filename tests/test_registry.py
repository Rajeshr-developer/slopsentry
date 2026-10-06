import asyncio

import pytest

from slopsentry.registry import normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Requests", "requests"),
        ("typing_extensions", "typing-extensions"),
        ("Typing.Extensions", "typing-extensions"),
        ("zope__.interface", "zope-interface"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize("name", ["Requests", "typing_extensions"])
def test_lookup_uses_normalised_name(make_client, name):
    async def go():
        client = make_client()
        try:
            return await client.get_project(name)
        finally:
            await client.aclose()

    assert asyncio.run(go()) is not None


def test_equivalent_names_share_cache(make_client):
    async def go():
        client = make_client()
        try:
            first = await client.get_project("typing_extensions")
            second = await client.get_project("Typing-Extensions")
            return first, second
        finally:
            await client.aclose()

    first, second = asyncio.run(go())
    assert first is second
