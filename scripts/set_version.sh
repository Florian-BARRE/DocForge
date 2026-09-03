#!/usr/bin/env bash
# ====== Code Summary ======
# Unified version bump — the ONE way to set the repo's version. Propagates a single X.Y.Z to every
# artifact (docforge app/worker, mcp, sdk) and refreshes the uv locks, so the three version sources
# never drift (the lockstep-release model: one `v*` tag ships all images AND the SDK at the same
# number). Usage: scripts/set_version.sh 0.13.0   then commit, then `git tag v0.13.0 && git push`.
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: scripts/set_version.sh X.Y.Z" >&2
  exit 2
fi
VERSION="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 1. docforge (app + worker share this pyproject) + mcp — the [project] version line.
sed -i -E "s/^version = \"[0-9]+\.[0-9]+\.[0-9]+\"/version = \"${VERSION}\"/" \
  "${ROOT}/src/docforge/pyproject.toml" "${ROOT}/src/mcp/pyproject.toml"

# 2. sdk — the single __version__ source of truth Hatchling reads.
sed -i -E "s/__version__ = \"[0-9]+\.[0-9]+\.[0-9]+\"/__version__ = \"${VERSION}\"/" \
  "${ROOT}/src/docforge_sdk/docforge_sdk/_version.py"

# 3. refresh the uv locks so the Docker `uv sync --frozen` builds don't fail on a stale lock.
( cd "${ROOT}/src/docforge" && uv lock >/dev/null )
( cd "${ROOT}/src/mcp" && uv lock >/dev/null )

echo "set version ${VERSION} across docforge, mcp, sdk (+ uv locks)."
echo "next: git add -A && git commit -m \"chore(release): ${VERSION}\" && git tag v${VERSION} && git push --follow-tags"
