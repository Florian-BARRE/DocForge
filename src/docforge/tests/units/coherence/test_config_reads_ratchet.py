"""RUNTIME_CONFIG read ratchet — safety net for the config-injection refactor (R-23).

Only the entry points and composition roots may read the process-global ``RUNTIME_CONFIG``; every
other module should receive its settings as parameters. Today many modules still reach for the
global (``RUNTIME_CONFIG.X`` after ``from config import RUNTIME_CONFIG``, or ``CONTEXT.RUNTIME_CONFIG``).
This test records, per file, how many such reads exist today (``config_reads_allowlist.json``) and:

  * fails when a file NOT in the allowlist reads the global (a new coupling to the global config);
  * fails when an allowlisted file reads it MORE often than recorded (a new read);
  * accepts fewer reads (R-23 removes them) — the allowlist is a ceiling, never a floor, and R-23
    shrinks it: lower the count (or drop the file) in the JSON as reads disappear.

A "read" is a load of the name ``RUNTIME_CONFIG`` or of an attribute ``.RUNTIME_CONFIG`` (so
``CONTEXT.RUNTIME_CONFIG`` and the ``config = CONTEXT.RUNTIME_CONFIG`` alias both count once). Imports,
annotations, assignments to ``CONTEXT.RUNTIME_CONFIG``, comments and docstrings are not reads.
Entry points and composition roots (see ``_ALLOWED_GLOBS``) are exempt.
"""

# ====== Standard Library Imports ======
import ast
import fnmatch
import json
import pathlib

# src/docforge/ (this uv project's root).
_SRC_ROOT = pathlib.Path(__file__).resolve().parents[3]
_ALLOWLIST_PATH = pathlib.Path(__file__).with_name("config_reads_allowlist.json")

_SCANNED_DIRS = ("app", "worker")
_GLOBAL_NAME = "RUNTIME_CONFIG"

# Entry points / composition roots / the config packages themselves: allowed to read the global.
_ALLOWED_GLOBS = (
    "app/entrypoint.py",
    "app/config/*",
    "app/backend/app.py",
    "app/backend/lifespan.py",
    "app/backend/context.py",
    "worker/entrypoint.py",
    "worker/config/*",
    "worker/backend/app.py",
    "worker/backend/lifespan.py",
    "worker/backend/context.py",
)


def _is_exempt(relative: str) -> bool:
    # fnmatch's ``*`` crosses ``/``, so ``app/config/*`` covers the whole package.
    return any(fnmatch.fnmatchcase(relative, glob) for glob in _ALLOWED_GLOBS)


class _ReadCounter(ast.NodeVisitor):
    """Counts loads of ``RUNTIME_CONFIG`` (bare or as an attribute), skipping imports/annotations."""

    def __init__(self) -> None:
        self.count = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 — ast API
        return

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 — ast API
        return

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 — ast API
        if node.value is not None:
            self.visit(node.value)

    def visit_arg(self, node: ast.arg) -> None:  # noqa: N802 — ast API
        return

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 — ast API
        if node.id == _GLOBAL_NAME and isinstance(node.ctx, ast.Load):
            self.count += 1

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 — ast API
        if node.attr == _GLOBAL_NAME and isinstance(node.ctx, ast.Load):
            self.count += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 — ast API
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 — ast API
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Return and parameter annotations are not reads; defaults, decorators and the body are.
        for child in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if child is not None:
                self.visit(child)
        for statement in node.body:
            self.visit(statement)


def _current_reads() -> dict[str, int]:
    """``{file relative to src/docforge: read count}`` for every non-exempt file that reads the global."""
    reads: dict[str, int] = {}
    for directory in _SCANNED_DIRS:
        for path in sorted((_SRC_ROOT / directory).rglob("*.py")):
            relative = path.relative_to(_SRC_ROOT).as_posix()
            if _is_exempt(relative):
                continue
            counter = _ReadCounter()
            counter.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            if counter.count:
                reads[relative] = counter.count
    return reads


def _allowlist() -> dict[str, int]:
    return json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))["reads"]


def test_no_new_file_reads_the_global_runtime_config() -> None:
    """A file outside the allowlist that reads ``RUNTIME_CONFIG`` is a new coupling to the global
    config: inject the value from the composition root instead."""
    allowed = _allowlist()
    new_files = sorted(set(_current_reads()) - set(allowed))
    assert not new_files, (
        f"These files read the global RUNTIME_CONFIG outside the entry points: {new_files}. "
        "Pass the setting in as a parameter instead of adding a read (R-23 shrinks the allowlist)."
    )


def test_no_allowlisted_file_adds_a_runtime_config_read() -> None:
    """An allowlisted file may keep or lower its recorded read count, never raise it."""
    allowed = _allowlist()
    grown = {
        file: f"{count} reads, allowed {allowed[file]}"
        for file, count in _current_reads().items()
        if file in allowed and count > allowed[file]
    }
    assert not grown, (
        f"New RUNTIME_CONFIG reads in allowlisted files: {grown}. "
        "Inject the value instead; lowering a count in config_reads_allowlist.json is the only edit allowed."
    )


def test_allowlist_has_no_stale_entry() -> None:
    """A file that no longer exists must leave the allowlist, so the ratchet only ever tightens."""
    missing = sorted(file for file in _allowlist() if not (_SRC_ROOT / file).is_file())
    assert not missing, f"config_reads_allowlist.json lists files that no longer exist: {missing}"
