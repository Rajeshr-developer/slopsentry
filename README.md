# SlopSentry

SlopSentry checks packages for **slopsquatting** before you install them: AI-hallucinated
package names and malicious lookalikes that attackers register to catch them.

## Install

```sh
pip install slopsentry
```

For development:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```sh
slopsentry check requests
```

Currently `check` verifies that the package exists on PyPI.

| Result | Meaning                       | Exit code |
| ------ | ----------------------------- | --------- |
| PASS   | package exists on PyPI        | 0         |
| FAIL   | package not found on PyPI     | 1         |
| WARN   | PyPI could not be reached     | 0 (2 with `--strict`) |

Names are normalised per PEP 503, so `Requests` and `typing_extensions` match
`requests` and `typing-extensions`.

Use `--strict` to treat an unreachable registry as a failure:

```sh
slopsentry check --strict requests
```
