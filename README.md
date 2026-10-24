# SlopSentry

SlopSentry checks packages for **slopsquatting** before you install them: AI-hallucinated
package names and malicious lookalikes that attackers register to catch them.

<!-- TODO: demo GIF of the Claude Code hook blocking a hallucinated package -->
<!-- ![SlopSentry blocking a hallucinated package in Claude Code](docs/demo.gif) -->

> **Alpha (0.1.0):** only Python package installs from PyPI are checked. npm and other
> ecosystems aren't supported yet.

## Install

SlopSentry needs Python 3.10 or newer. Install it as a standalone tool with
[pipx](https://pipx.pypa.io/):

```sh
pipx install slopsentry
```

or run it without installing, using [uv](https://docs.astral.sh/uv/):

```sh
uvx slopsentry check requests
```

`pip install slopsentry` works too.

For development:

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```sh
slopsentry check requests
```

`check` runs every check, adds up the risk points, and gives a verdict:

| Check     | Flags                                                 | Points |
| --------- | ----------------------------------------------------- | ------ |
| exists    | package not found on PyPI                             | 100    |
| age       | first release under 90 days ago, or no released files | 40     |
| age       | two or fewer releases                                 | 20     |
| age       | no homepage or repository link                        | 20     |
| lookalike | resembles a popular package (see below)               | 50     |
| lookalike | resembles one, but the age check passes cleanly       | 15     |

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

### Lookalike check

The lookalike check compares the name with the 5,000 most-downloaded PyPI packages,
bundled in `slopsentry/data/top_pypi.json`. Popular packages are never flagged, so
`requests` passes even though it's close to other names. A name is flagged if:

- it differs from a popular name only by separators (`django-rest-framework` vs
  `djangorestframework`),
- it adds or removes `py-`, `python-`, `-py`, `-python` or `-lib` (`python-requests`,
  `pandas-py`), or
- it's within Damerau-Levenshtein distance 1 of a popular name, or 2 for names longer
  than 10 characters (`reqeusts`, `numpyy`).

Two guards cut false positives on legitimate packages:

1. **Short names:** names under 5 characters get no edit-distance matching, since almost
   every short name is one edit from another (`sax`/`six`, `od`/`id`).
2. **Package families:** a distance-2 match is ignored when the names differ in exactly
   one whole `-` segment, such as `mypy-boto3-emr` and `mypy-boto3-ec2`.

The reason names the package it resembles, e.g. "looks like requests". If the package is
established (the age check passes cleanly), the match adds only 15 points and reads
"looks like requests (established package)": shown in `--explain`, but not enough to warn
by itself. A new or thin lookalike adds 50, so one that is also brand new blocks.

To refresh the bundled list (it needs the network, or a downloaded copy of the dataset):

```sh
.venv/bin/python scripts/update_top_packages.py
```

`PACKAGE` can be a full requirement: `requests==2.31.0` and `requests[socks]` are
checked as `requests`. Invalid input is rejected before any request is made.

Names are normalised per PEP 503, so `Requests` and `typing_extensions` match
`requests` and `typing-extensions`.

Use `--strict` to treat an unreachable registry as a failure:

```sh
slopsentry check --strict requests
```

## Claude Code hook

`slopsentry hook` is a Claude Code `PreToolUse` hook. It reads the hook event on stdin,
finds install commands in Bash tool calls, scores each package, and answers on stdout:

| Worst verdict | Decision                                         |
| ------------- | ------------------------------------------------ |
| BLOCK         | `deny`, with the package, score and reasons      |
| WARN          | `ask`, so you confirm before it runs             |
| PASS          | allowed silently                                 |

It recognises `pip install` (also `pip3`, `python -m pip`, `python3 -m pip`), `uv add`,
`uv pip install` and `poetry add`, including in chained commands (`&&`, `||`, `;`, `|`)
and after `sudo`, `env` or `VAR=value` prefixes. Flags, local paths, URLs, `-e` and `-r`
arguments are skipped. Commands that use a custom index (`--index-url`, `-i`,
`--extra-index-url`, `-f`/`--find-links`, uv's `--index`/`--default-index`, poetry's
`--source`) aren't checked, since their packages may not be on PyPI. In 0.1.0 only
Python installs are checked; `npm install`, `yarn add` and other ecosystems pass through
unchecked.

The hook fails open: it always exits 0. Commands it can't parse, registry errors (5 second
timeout) and its own crashes all allow the command. Crashes are appended with a timestamp
to `~/.slopsentry/hook.log`; add `--debug` to also print them to stderr.

### Setting up the hook

1. Install SlopSentry so `slopsentry` is on your `PATH`:

   ```sh
   pipx install slopsentry
   slopsentry --help
   ```

2. Add the hook to `.claude/settings.json` in a project, or to `~/.claude/settings.json`
   to cover every project:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "slopsentry hook || true",
               "timeout": 30
             }
           ]
         }
       ]
     }
   }
   ```

   `|| true` keeps Claude Code working if `slopsentry` isn't installed on a machine
   where the settings file is shared.

3. Restart Claude Code, then check it in `/hooks`. Asking Claude to run
   `pip install reqeusts` should be blocked.

If you use uv and don't want to install anything, use `"command": "uvx slopsentry hook || true"`
instead. The first run downloads SlopSentry, so it's slower.

When working on SlopSentry itself, point the hook at your checkout instead:
`"\"$CLAUDE_PROJECT_DIR\"/.venv/bin/slopsentry hook || true"`.

### Known gaps

The hook reads the command text; it doesn't run a shell. These installs get past it:

- **`bash -c "pip install x"`** (and `sh -c`, `eval`): the install is inside a string
  argument that isn't parsed.
- **`$(...)` and backtick subshells**, e.g. `pip install $(cat pkgs.txt)`: the package
  names only exist once the shell runs.
- **`xargs`**, e.g. `cat pkgs.txt | xargs pip install`: the names arrive on stdin.
- **`-r requirements.txt`**: requirement files aren't read, so their packages aren't
  checked.
- **`--extra-index-url` dependency confusion**: commands with an extra index are skipped
  entirely. pip picks the highest version across all indexes, so an attacker can publish
  your private package's name on PyPI with a higher version, and it wins.

## Data attribution

`slopsentry/data/top_pypi.json` is derived from
[Top PyPI Packages](https://hugovk.dev/top-pypi-packages/) by Hugo van Kemenade and
contributors ([DOI 10.5281/zenodo.23082845](https://doi.org/10.5281/zenodo.23082845)),
release 2026.10.1, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changes: kept the top 5,000
names in download order, normalised them per PEP 503, and removed the download counts.
