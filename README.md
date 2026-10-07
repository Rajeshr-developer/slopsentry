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
`--source`) aren't checked, since their packages may not be on PyPI. npm isn't
supported yet.

The hook fails open: it always exits 0. Commands it can't parse, registry errors (5 second
timeout) and its own crashes all allow the command. Crashes are appended with a timestamp
to `~/.slopsentry/hook.log`; add `--debug` to also print them to stderr.

To use it in a project, add this to `.claude/settings.json` (this repo already does):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.venv/bin/slopsentry hook || true",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

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
