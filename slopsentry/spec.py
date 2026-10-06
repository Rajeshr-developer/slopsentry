"""Parse package arguments like `requests==2.31.0` or `requests[socks]` into a name."""

from packaging.requirements import InvalidRequirement, Requirement


class InvalidPackageSpec(ValueError):
    """The argument is not a valid package name or requirement."""


def parse_package_name(spec: str) -> str:
    """Return the project name from a requirement string, dropping extras, versions and markers."""
    if not spec.strip():
        raise InvalidPackageSpec("package name is empty")
    try:
        return Requirement(spec).name
    except InvalidRequirement as exc:
        reason = str(exc).splitlines()[0]
        raise InvalidPackageSpec(f"invalid package spec {spec!r}: {reason}") from exc
