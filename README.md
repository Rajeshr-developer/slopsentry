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

`check` runs every check, adds up the risk points, and gives a verdict:

| Check  | Flags                                                   | Points |
| ------ | ------------------------------------------------------- | ------ |
| exists | package not found on PyPI                               | 100    |
| age    | first release under 90 days ago, or no released files   | 40     |
| age    | two or fewer releases                                   | 20     |
| age    | no homepage or repository link                          | 20     |

| Verdict | Total points | Exit code |
| ------- | ------------ | --------- |
| PASS    | under 30     | 0         |
| WARN    | 30 to 69     | 0         |
| BLOCK   | 70 or more   | 1         |

If PyPI can't be reached, the package can't be verified: the verdict is at least WARN and
the exit code 0, or ERROR with exit code 2 under `--strict`. Empty or invalid input is an
ERROR with exit code 2. Thresholds live in `slopsentry/scoring.py`.

Without `--explain`, `check` prints one summary line plus the reasons for a WARN or
BLOCK. With `--explain` it prints a table of every check's status, detail and points:

```sh
slopsentry check --explain requests
```

`PACKAGE` can be a full requirement: `requests==2.31.0` and `requests[socks]` are
checked as `requests`. Invalid input is rejected before any request is made.

Names are normalised per PEP 503, so `Requests` and `typing_extensions` match
`requests` and `typing-extensions`.

Use `--strict` to treat an unreachable registry as a failure:

```sh
slopsentry check --strict requests
```
