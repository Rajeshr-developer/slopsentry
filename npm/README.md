# slopsentry (npm wrapper)

This package is a thin wrapper around [SlopSentry](https://github.com/Rajeshr-developer/slopsentry),
a Python CLI that checks packages for **slopsquatting** (AI-hallucinated package names and
malicious lookalikes) before they're installed.

It contains no checking logic of its own. The `slopsentry` command runs
`uvx slopsentry@<version>` and passes every argument, stdin, stdout and the exit code
straight through, so it behaves exactly like the Python tool.

The Python version is pinned to this package's version: `slopsentry@0.1.0` on npm always
runs `slopsentry==0.1.0` from PyPI, never whatever uv happens to have cached.

> **Alpha (0.1.0):** SlopSentry only checks Python package installs from PyPI. It doesn't
> check npm packages yet, despite being installable from npm.

## Requirements

- Node.js 18 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which provides `uvx`.
  uv downloads Python and SlopSentry on first run, so the first call is slower.

If `uvx` isn't on your `PATH`, the wrapper prints install instructions and exits with
code 127.

## Usage

```sh
npx slopsentry check requests
npx slopsentry check --explain reqeusts
```

or install it globally:

```sh
npm install -g slopsentry
slopsentry check requests
```

As a Claude Code `PreToolUse` hook, use `"command": "npx -y slopsentry hook || true"`.
See the [main README](https://github.com/Rajeshr-developer/slopsentry#claude-code-hook)
for the full setup and what the hook checks.

## Prefer the Python package

If you have Python, installing it directly avoids the Node and uv layers:

```sh
pipx install slopsentry
```

## License

MIT
