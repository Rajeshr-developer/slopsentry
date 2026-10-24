#!/usr/bin/env node
// Thin wrapper: runs the Python SlopSentry CLI through uvx, passing every argument through.

"use strict";

const { spawn } = require("node:child_process");
const { version } = require("../package.json");

// Pinned to the npm package version, so each npm release runs the matching PyPI release.
const pkg = `slopsentry@${version}`;

const child = spawn("uvx", [pkg, ...process.argv.slice(2)], { stdio: "inherit" });

child.on("error", (err) => {
  if (err.code === "ENOENT") {
    console.error(
      [
        "slopsentry: uv is not installed (the `uvx` command wasn't found on PATH).",
        "",
        "This npm package is a wrapper that runs the Python tool with uv. Install uv:",
        "  macOS / Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh",
        '  Windows:        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"',
        "  or see https://docs.astral.sh/uv/getting-started/installation/",
        "",
        "Or install SlopSentry directly with: pipx install slopsentry",
      ].join("\n"),
    );
    process.exit(127);
  }
  console.error(`slopsentry: failed to run uvx: ${err.message}`);
  process.exit(1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 1);
  }
});
