# ====== Code Summary ======
# Coherence ratchet — the PUBLIC repo must expose ONLY code + product docs. This makes it IMPOSSIBLE to
# merge a commit that (a) TRACKS an internal dev-process artifact (the audit journal, the RPI notes,
# the private UI-screenshot tooling, the retired agent-memory snapshots, the local MCP client config) or
# (b) leaves a tracked file pointing at an internal-only path. The AI Dev Kit's own files (CLAUDE.md,
# .claude/settings.json, .codex/config.toml) are tracked on purpose. It closes the recurrence of internal artifacts being committed (the reason
# AUDIT-REMEDIATION.md + docs/rpi/ had to be un-tracked). Serviceless: shells out to git against the
# checkout; skips cleanly when run outside a git working tree (e.g. a source tarball).

# ====== Standard Library Imports ======
import pathlib
import shutil
import subprocess

# ====== Third-Party Library Imports ======
import pytest

# tests/units/coherence/<this> → parents[3] is src/docforge; its parents[1] is the repo root.
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
_REPO_ROOT = _SRC_ROOT.parents[1]
_THIS = str(pathlib.Path(__file__).resolve().relative_to(_REPO_ROOT))

# Internal artifacts that must NEVER be tracked (gitignored, kept local).
_FORBIDDEN_TRACKED_EXACT = {
    ".mcp.json",  # local MCP client config
    "AUDIT-REMEDIATION.md",  # internal remediation journal
    "src/docforge/app/frontend/UI-SCREENSHOT.md",
    "src/docforge/app/frontend/scripts/ui-shot.mjs",
}
_FORBIDDEN_TRACKED_PREFIXES = (
    "docs/rpi/",  # RPI research/plan/implementation notes
    "docs/archive/agent-memory-legacy/",
)

# Pointers to internal-only paths a tracked file must not carry. The ignore rules, the AGENTS.md rule
# and THIS ratchet legitimately name these strings — allowlist them.
_LEAK_ALLOWLIST = {".gitignore", "AGENTS.md", _THIS}
_PATH_LEAK = r"agent-memory|\.claude/rules|\.claude/agent-memory|\.claude/commands"

_NOT_A_CHECKOUT = shutil.which("git") is None or not (_REPO_ROOT / ".git").exists()


def _git(*args: str) -> str:
    """Run a read-only git command at the repo root and return its stdout (never raises on non-zero)."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), *args], capture_output=True, text=True, check=False
    )
    return result.stdout


def _forbidden_tracked(paths: list[str]) -> list[str]:
    """Return, sorted, the paths that are internal artifacts (exact files or directory prefixes)."""
    return sorted(
        p
        for p in paths
        if p in _FORBIDDEN_TRACKED_EXACT or p.startswith(_FORBIDDEN_TRACKED_PREFIXES)
    )


@pytest.mark.parametrize("path", ["CLAUDE.md", ".claude/settings.json", ".codex/config.toml"])
def test_kit_files_may_be_tracked(path: str) -> None:
    """The AI Dev Kit's files are tracked like in the kit's other projects."""
    assert _forbidden_tracked([path, "README.md"]) == []


@pytest.mark.parametrize(
    "path",
    [
        ".mcp.json",
        "AUDIT-REMEDIATION.md",
        "docs/rpi/plan.md",
        "docs/archive/agent-memory-legacy/x.md",
    ],
)
def test_internal_notes_count_as_internal(path: str) -> None:
    """The internal dev-process notes are artifacts that must never be tracked."""
    assert _forbidden_tracked([path, "README.md"]) == [path]


@pytest.mark.skipif(_NOT_A_CHECKOUT, reason="not a git checkout")
def test_no_internal_artifact_is_tracked() -> None:
    """No internal dev-process artifact may be tracked by git in the public repo."""
    # 1. Every tracked path, matched against the exact-file set and the directory prefixes.
    bad = _forbidden_tracked(_git("ls-files").splitlines())
    assert not bad, (
        "internal artifacts are tracked in the PUBLIC repo — `git rm --cached` them and confirm they "
        f"are gitignored: {bad}"
    )


@pytest.mark.skipif(_NOT_A_CHECKOUT, reason="not a git checkout")
def test_no_tracked_file_leaks_an_internal_reference() -> None:
    """No tracked file may point at an internal-only path."""
    # 1. git grep (tracked working-tree files) for the internal paths.
    hits = set(_git("grep", "-lIE", _PATH_LEAK).splitlines())
    # 2. Drop the files that legitimately name these strings (ignore rules, AGENTS.md, this ratchet).
    leaked = sorted(h for h in hits if h not in _LEAK_ALLOWLIST)
    assert not leaked, (
        "tracked files reference internal-only paths/artifacts (reword the comment to drop the "
        f"internal pointer): {leaked}"
    )
