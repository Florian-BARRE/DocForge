# ====== Code Summary ======
# Throwaway client environments of the contract tests: a client this project does not depend on
# (the mcp 1.x Python client, the OpenAI Agents SDK) runs as a script in a `uv run --no-project
# --isolated --with ...` environment, frozen by exact pins plus `--exclude-newer`, so a new
# upstream release of a pinned package or of any transitive one never changes the result. Building
# an environment needs uv and the package index (or uv's cache): it skips, with the reason, only
# when uv cannot reach the index, and fails otherwise.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
import subprocess
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# Resolution cut-off of every throwaway env: only packages uploaded before it are considered, so
# the transitive dependencies of the pins below are frozen too. Move it with the pins.
EXCLUDE_NEWER = "2026-10-28T00:00:00Z"
# The last mcp 1.x: what a client locked before mcp 2.0 (or on the 1.x maintenance line) runs.
MCP_1X_REQUIREMENT = "mcp==1.29.1"
# What this server locks and what openai-agents 0.24.0 resolves to (mcp>=2,<3).
MCP_2X_REQUIREMENT = "mcp==2.3.0"
# uv's own wording when the index cannot be reached (connect or DNS error) or the network is off
# and the cache lacks a package: the only failures that skip instead of failing.
_UV_NETWORK_ERRORS = ("error sending request for url", "network was disabled")


def uv_run(
    requirements: list[str], *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `python -I <args>` in a throwaway env holding exactly `requirements`."""
    with_args = [arg for requirement in requirements for arg in ("--with", requirement)]
    return subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--isolated",
            "--exclude-newer",
            EXCLUDE_NEWER,
            *with_args,
            "python",
            "-I",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )


def build_client_env(
    requirements: list[str], probe_import: str, env: dict[str, str] | None = None
) -> None:
    """Resolve the throwaway env; skip when uv cannot reach the package index, fail otherwise."""
    completed = uv_run(requirements, "-c", f"import {probe_import}", env=env)
    if completed.returncode != 0 and any(e in completed.stderr for e in _UV_NETWORK_ERRORS):
        pytest.skip(f"uv cannot reach the package index: {completed.stderr.strip()[-600:]}")
    assert completed.returncode == 0, completed.stderr[-4000:]


def run_client_script(
    requirements: list[str], probe_import: str, script: Path, *args: str
) -> dict[str, Any]:
    """Run a client script in its throwaway env and return the JSON report of its last line."""
    build_client_env(requirements, probe_import)
    completed = uv_run(requirements, str(script), *args)
    assert completed.returncode == 0, completed.stderr[-4000:]
    report: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
    return report
