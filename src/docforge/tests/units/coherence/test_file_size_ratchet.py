# ====== Code Summary ======
# File-size ratchet (coding standards, principle 3: "400 lines at most"). Scans every ``*.py`` under
# ``src/`` and every ``*.ts``/``*.tsx`` under the frontend's ``src/`` (generated code and the Alembic
# migration revisions excluded) and fails when (a) a file NOT in ``file_size_allowlist.json`` crosses
# 400 lines, or (b) an allowlisted file grows past its recorded size. The allowlist is a CEILING, never
# a floor: splitting a file lets you lower its number (or drop it once it is back to 400 lines or fewer;
# the stale-entry test then forces that edit), nobody raises one. It lists today's reality, found when
# the ratchet was written (R-33 already split the frontend's oversized files, so none remains there).
# A "line" is what ``str.splitlines`` counts; ``.venv``/``node_modules``/build outputs are not scanned.

# ====== Standard Library Imports ======
import fnmatch
import json
import os
import pathlib

# ====== Local Project Imports ======
from .support.import_scan import SRC_ROOT

# The repository's ``src/`` (src/docforge's parent) and the frontend source root.
_SRC = SRC_ROOT.parent
_REPO = _SRC.parent
_ALLOWLIST_PATH = pathlib.Path(__file__).with_name("file_size_allowlist.json")

MAX_LINES = 400
_PRUNED_DIRS = frozenset(
    {".venv", "node_modules", "__pycache__", "dist", "build", ".git", ".pytest_cache"}
)
_FRONTEND_SRC = "src/docforge/app/frontend/src/"

# Never counted: generated code (rewritten by a tool, not by hand) and the migration revisions
# (frozen history: a revision is never split, and the squashed initial schema is long by nature).
_EXCLUDED_GLOBS = (
    "src/docforge/app/frontend/src/api/generated.ts",
    "src/docforge/shared/migrations/versions/*",
)


def _is_scanned(relative: str) -> bool:
    if any(fnmatch.fnmatchcase(relative, glob) for glob in _EXCLUDED_GLOBS):
        return False
    if relative.endswith(".py"):
        return True
    return relative.startswith(_FRONTEND_SRC) and relative.endswith((".ts", ".tsx"))


def _line_count(path: pathlib.Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _sizes() -> dict[str, int]:
    """``{path relative to the repo root: line count}`` of every scanned file over ``MAX_LINES``."""
    oversized: dict[str, int] = {}
    for directory, subdirs, files in os.walk(_SRC):
        subdirs[:] = [name for name in subdirs if name not in _PRUNED_DIRS]
        for name in files:
            path = pathlib.Path(directory, name)
            relative = path.relative_to(_REPO).as_posix()
            if _is_scanned(relative) and (lines := _line_count(path)) > MAX_LINES:
                oversized[relative] = lines
    return oversized


def _allowlist() -> dict[str, int]:
    return json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))["max_lines"]


def test_no_new_file_crosses_the_size_limit() -> None:
    """A file outside the allowlist over 400 lines: split it (one responsibility per unit)."""
    new = {file: lines for file, lines in _sizes().items() if file not in _allowlist()}
    assert not new, (
        f"Files over {MAX_LINES} lines and not allowlisted: {new}. Split them into a sub-package "
        "(coding standards, principle 3); never add them to file_size_allowlist.json."
    )


def test_no_allowlisted_file_grows() -> None:
    """An allowlisted file may keep or lower its recorded size, never raise it."""
    allowed = _allowlist()
    grown = {
        file: f"{lines} lines, allowed {allowed[file]}"
        for file, lines in _sizes().items()
        if file in allowed and lines > allowed[file]
    }
    assert not grown, (
        f"Allowlisted files that grew: {grown}. Move code out instead; lowering a number in "
        "file_size_allowlist.json is the only edit allowed."
    )


def test_allowlist_has_no_stale_entry() -> None:
    """A file that is gone, or back to 400 lines or fewer, must leave the allowlist."""
    sizes = _sizes()
    stale = sorted(file for file in _allowlist() if file not in sizes)
    assert not stale, (
        f"file_size_allowlist.json lists files that are gone or now within {MAX_LINES} lines: {stale}. "
        "Delete the entries."
    )


def test_excluded_paths_are_real_and_the_scan_sees_the_sources() -> None:
    """The exclusions must name existing files (a rename must not silently re-include them) and the
    scan must reach python and frontend sources."""
    assert (_REPO / "src/docforge/app/frontend/src/api/generated.ts").is_file()
    assert any(_REPO.joinpath("src/docforge/shared/migrations/versions").glob("*.py"))
    assert _is_scanned("src/docforge/worker/entrypoint.py")
    assert _is_scanned("src/docforge/app/frontend/src/main.tsx")
    assert not _is_scanned("src/docforge/app/frontend/vite.config.ts")
