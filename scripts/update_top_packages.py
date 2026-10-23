"""Refresh slopsentry/data/top_pypi.json from the top-pypi-packages dataset.

Needs the network unless given a downloaded copy; never run from tests. Usage:

    .venv/bin/python scripts/update_top_packages.py [top-pypi-packages.min.json]
"""

import json
import sys
from pathlib import Path

import httpx

from slopsentry.registry import normalize_name

SOURCE_URL = "https://hugovk.dev/top-pypi-packages/top-pypi-packages.min.json"
COUNT = 5000
OUT = Path(__file__).resolve().parent.parent / "slopsentry" / "data" / "top_pypi.json"


def main() -> None:
    if len(sys.argv) > 1:
        dataset = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        dataset = httpx.get(SOURCE_URL, follow_redirects=True, timeout=60).raise_for_status().json()

    names: list[str] = []
    seen: set[str] = set()
    for row in dataset["rows"]:  # already sorted by downloads, most first
        name = normalize_name(row["project"])
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) == COUNT:
            break

    snapshot = {
        "source": SOURCE_URL,
        "dataset": "Top PyPI Packages by Hugo van Kemenade et al.",
        "license": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)",
        "changes": f"Top {COUNT} names kept in download order, normalised per PEP 503; "
        "download counts removed.",
        "last_update": dataset["last_update"],
        "count": len(names),
        "packages": names,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(names)} packages from {dataset['last_update']} to {OUT}")


if __name__ == "__main__":
    main()
