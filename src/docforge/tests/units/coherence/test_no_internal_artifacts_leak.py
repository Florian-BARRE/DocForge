# ====== Code Summary ======
# Coherence ratchet — the PUBLIC repo must expose ONLY code + product docs. This makes it IMPOSSIBLE to
# merge a commit that (a) TRACKS an internal / AI-workflow artifact (the Claude setup, the audit
# journal, the RPI notes, the private UI-screenshot tooling) or (b) leaves a tracked file pointing at
# an internal-only path. It closes the recurrence of internal artifacts being committed (the reason
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

# Internal artifacts that must NEVER be tracked (kept private + backed up via scripts/backup-claude.sh).
_FORBIDDEN_TRACKED_EXACT = {
    "CLAUDE.md",  # root AI project instructions (gitignored /CLAUDE.md)
    ".mcp.json",
    "AUDIT-REMEDIATION.md",  # internal remediation journal
    "src/docforge/app/frontend/UI-SCREENSHOT.md",
    "src/docforge/app/frontend/scripts/ui-shot.mjs",
}
_FORBIDDEN_TRACKED_PREFIXES = (
    ".claude/",  # the whole Claude setup
    "docs/rpi/",  # RPI research/plan/implementation notes
    "docs/archive/agent-memory-legacy/",
)

# Content leaks a tracked file must not carry. The ignore rules, the backup tool and THIS ratchet
# legitimately name these strings — allowlist them.
_LEAK_ALLOWLIST = {".gitignore", "scripts/backup-claude.sh", _THIS}
_HARD_LEAK = r"claude\.ai/code|Co-Authored-By: Claude|Claude-Session|Generated with \[Claude"
_PATH_LEAK = r"agent-memory|\.claude/rules|\.claude/agent-memory|\.claude/commands"

_NOT_A_CHECKOUT = shutil.which("git") is None or not (_REPO_ROOT / ".git").exists()


def _git(*args: str) -> str:
    """Run a read-only git command at the repo root and return its stdout (never raises on non-zero)."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), *args], capture_output=True, text=True, check=False
    )
    return result.stdout


@pytest.mark.skipif(_NOT_A_CHECKOUT, reason="not a git checkout")
def test_no_internal_artifact_is_tracked() -> None:
    """No internal / AI-workflow artifact may be tracked by git in the public repo."""
    # 1. Every tracked path, matched against the exact-file set and the directory prefixes.
    tracked = _git("ls-files").splitlines()
    bad = sorted(
        p
        for p in tracked
        if p in _FORBIDDEN_TRACKED_EXACT or p.startswith(_FORBIDDEN_TRACKED_PREFIXES)
    )
    assert not bad, (
        "internal artifacts are tracked in the PUBLIC repo — `git rm --cached` them and confirm they "
        f"are gitignored (they persist via scripts/backup-claude.sh): {bad}"
    )


@pytest.mark.skipif(_NOT_A_CHECKOUT, reason="not a git checkout")
def test_no_tracked_file_leaks_an_internal_reference() -> None:
    """No tracked file may point at an internal-only path or carry Claude attribution."""
    # 1. git grep (tracked working-tree files) for each leak family; union the hit filenames.
    hits: set[str] = set()
    for pattern in (_HARD_LEAK, _PATH_LEAK):
        hits.update(_git("grep", "-lIE", pattern).splitlines())
    # 2. Drop the files that legitimately name these strings (ignore rules, backup tool, this ratchet).
    leaked = sorted(h for h in hits if h not in _LEAK_ALLOWLIST)
    assert not leaked, (
        "tracked files reference internal-only paths/artifacts (reword the comment to drop the "
        f"internal pointer): {leaked}"
    )
