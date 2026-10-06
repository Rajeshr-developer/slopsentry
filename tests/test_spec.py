import pytest

from slopsentry.spec import InvalidPackageSpec, parse_package_name


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("requests", "requests"),
        ("requests==2.31.0", "requests"),
        ("requests[socks]", "requests"),
        ("requests[socks,security]>=2,<3", "requests"),
        ("Requests; python_version >= '3.8'", "Requests"),
        ("pkg @ https://example.com/pkg-1.0-py3-none-any.whl", "pkg"),
    ],
)
def test_parse_package_name(spec, expected):
    assert parse_package_name(spec) == expected


@pytest.mark.parametrize("spec", ["", "   "])
def test_empty_name_rejected(spec):
    with pytest.raises(InvalidPackageSpec, match="package name is empty"):
        parse_package_name(spec)


@pytest.mark.parametrize("spec", ["==1.0", "requests==", "-bad", "foo bar", "req/uests"])
def test_invalid_spec_rejected(spec):
    with pytest.raises(InvalidPackageSpec, match="invalid package spec"):
        parse_package_name(spec)
