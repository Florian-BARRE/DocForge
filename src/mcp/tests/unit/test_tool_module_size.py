# ====== Code Summary ======
# Structure guard for the MCP tool modules: each file stays within the 400-line unit size and no
# single register function grows back into a giant closure (R-26). The registered catalogue itself
# is pinned by tests/characterization.

from __future__ import annotations

# ====== Standard Library Imports ======
import ast
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "libs" / "tools"
MAX_FILE_LINES = 400
# A register function holds the tool docstrings (long by design), so the bound is generous: it
# only stops one function from absorbing a whole domain again.
MAX_REGISTER_FUNCTION_LINES = 190


def _tool_files() -> list[Path]:
    return sorted(TOOLS_DIR.rglob("*.py"))


def test_tool_files_stay_within_the_unit_size() -> None:
    oversized = {
        str(path.relative_to(TOOLS_DIR)): len(path.read_text().splitlines())
        for path in _tool_files()
        if len(path.read_text().splitlines()) > MAX_FILE_LINES
    }
    assert oversized == {}


def test_no_register_function_is_a_giant_closure() -> None:
    oversized: dict[str, int] = {}
    for path in _tool_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("register"):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length > MAX_REGISTER_FUNCTION_LINES:
                    oversized[f"{path.relative_to(TOOLS_DIR)}::{node.name}"] = length
    assert oversized == {}
