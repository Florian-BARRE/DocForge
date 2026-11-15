# ====== Code Summary ======
# Shared AST import scanner of the architecture ratchets (node purity, layers, IR canonical). It
# lists EVERY import of a Python file — function-local and ``TYPE_CHECKING`` ones included, because
# a lazy import is exactly how a forbidden edge hides — and resolves a relative import to the
# directory it points at. Pure parsing: nothing is imported or executed.

# ====== Standard Library Imports ======
import ast
import pathlib
from dataclasses import dataclass

# src/docforge/ (this uv project's root): tests/units/coherence/support/ -> parents[4].
SRC_ROOT = pathlib.Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ImportRef:
    """One ``import`` / ``from ... import`` statement.

    Attributes:
        module (str): The dotted module as written (``""`` for ``from . import x``).
        level (int): The number of leading dots (0 for an absolute import).
        names (tuple[str, ...]): The imported names (``from m import a, b``); empty for ``import m``.
        lineno (int): The statement's line.
    """

    module: str
    level: int
    names: tuple[str, ...]
    lineno: int


class ImportScanner:
    """Static, side-effect-free listing of the imports of a source file."""

    @staticmethod
    def parse(path: pathlib.Path) -> ast.Module:
        """Parse a Python file (UTF-8) into its AST."""
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    @classmethod
    def imports_of(cls, path: pathlib.Path) -> list[ImportRef]:
        """Every import anywhere in the file's body, in source order."""
        return cls.imports_in(cls.parse(path))

    @staticmethod
    def imports_in(tree: ast.AST) -> list[ImportRef]:
        """Every import of an already-parsed tree, in source order."""
        found: list[ImportRef] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(ImportRef(alias.name, 0, (), node.lineno) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names = tuple(alias.name for alias in node.names)
                found.append(ImportRef(node.module or "", node.level, names, node.lineno))
        return sorted(found, key=lambda ref: ref.lineno)

    @staticmethod
    def relative_target(path: pathlib.Path, ref: ImportRef) -> pathlib.Path:
        """The directory a relative import climbs to (``from .. import x`` in ``a/b/c.py`` -> ``a``).

        Raises:
            ValueError: ``ref`` is not a relative import.
        """
        if not ref.level:
            raise ValueError(f"{ref} is not a relative import")
        base = path.parent
        for _ in range(ref.level - 1):
            base = base.parent
        return base

    @staticmethod
    def under(module: str, prefix: str) -> bool:
        """True when the dotted ``module`` is ``prefix`` or sits below it."""
        return module == prefix or module.startswith(f"{prefix}.")

    @staticmethod
    def python_files(root: pathlib.Path) -> list[pathlib.Path]:
        """Every ``*.py`` below ``root``, sorted (``__pycache__`` skipped)."""
        return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
