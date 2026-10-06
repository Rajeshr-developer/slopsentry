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

`check` verifies that the package exists on PyPI, then warns if it looks freshly
registered: first release under 90 days ago, two or fewer releases, or no homepage or
repository link. Warnings are informational for now and don't change the exit code.

| Result | Meaning                       | Exit code |
| ------ | ----------------------------- | --------- |
| PASS   | package exists on PyPI        | 0         |
| FAIL   | package not found on PyPI     | 1         |
| WARN   | PyPI could not be reached     | 0 (2 with `--strict`) |
| ERROR  | empty or invalid package spec | 2         |

`PACKAGE` can be a full requirement: `requests==2.31.0` and `requests[socks]` are
checked as `requests`. Invalid input is rejected before any request is made.

Names are normalised per PEP 503, so `Requests` and `typing_extensions` match
`requests` and `typing-extensions`.

Use `--strict` to treat an unreachable registry as a failure:

```sh
slopsentry check --strict requests
```
