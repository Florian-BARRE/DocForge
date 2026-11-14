# ====== Code Summary ======
# Characterization of the data layer's facade surface (safety net for the refactoring campaign): the
# 26 facade attributes of ``Database``, each facade's class name and the public callables it exposes
# (kind + name + signature), frozen as a table. A facade split that renames or moves a public method
# fails here. A second guard scans the facade modules' imports: the data layer must not depend on
# the app or worker packages. No database: the three store clients are mocks.

# ====== Standard Library Imports ======
import ast
import pathlib
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.services.db.database import Database

# ====== Local Project Imports ======
from .support.facade_surface import FacadeSurfaceReader
from .support.facade_surface_golden import FACADE_SURFACE

FACADES_DIR = (
    pathlib.Path(__file__).resolve().parents[4] / "shared" / "libs" / "services" / "db" / "facades"
)

#: Top-level packages that belong to the app / worker (or are their import aliases): the shared data
#: layer must never import them. ``shared_libs`` is the shared package and stays allowed.
FORBIDDEN_ROOTS = frozenset(
    {"app", "worker", "backend", "config", "base_config", "libs", "entrypoint", "docforge"}
)

#: A relative import climbing past ``shared_libs`` (facades/ -> db/ -> services/ -> shared_libs/) would
#: leave the shared package: level 3 is the highest legitimate one.
MAX_RELATIVE_LEVEL = 3

FROZEN_FACADE_ATTRIBUTES = (
    "artifact_cache",
    "audit",
    "auth",
    "collection_aliases",
    "collections",
    "config_history",
    "documents",
    "enablement",
    "filters",
    "idempotency",
    "index_rebuild",
    "index_state",
    "ingestion",
    "jobs",
    "meta_vectors",
    "metadata_edit",
    "metadata_values",
    "replay_persist",
    "replay_source",
    "schema_changes",
    "search",
    "storage",
    "store_rebuild",
    "trace_payloads",
    "transfer",
    "transfer_tracker",
)


@pytest.fixture(scope="module")
def database() -> Database:
    """A Database wired with mocked store clients (the facades only hold them, nothing connects)."""
    return Database(MagicMock(), MagicMock(), MagicMock())


def _facade_attributes(database: Database) -> tuple[str, ...]:
    return tuple(
        sorted(name for name in vars(database) if not name.startswith("_") and name != "logger")
    )


def test_database_exposes_the_26_frozen_facade_attributes(database: Database) -> None:
    """``Database`` carries exactly the frozen facade attributes: none dropped, renamed or added."""
    assert _facade_attributes(database) == FROZEN_FACADE_ATTRIBUTES
    assert len(FROZEN_FACADE_ATTRIBUTES) == 26


def test_database_own_public_methods_are_the_two_lifecycle_calls(database: Database) -> None:
    """Besides its facades, ``Database`` itself only exposes ensure_object_store() and close()."""
    assert FacadeSurfaceReader.lines_of(database) == (
        "async close() -> None",
        "async ensure_object_store() -> None",
    )


def test_golden_covers_exactly_the_frozen_facade_attributes() -> None:
    """The surface table has one entry per frozen attribute, no stale one."""
    assert tuple(sorted(FACADE_SURFACE)) == FROZEN_FACADE_ATTRIBUTES


@pytest.mark.parametrize("attribute", FROZEN_FACADE_ATTRIBUTES)
def test_facade_class_name_is_unchanged(database: Database, attribute: str) -> None:
    """Each ``Database`` attribute still holds the same facade class."""
    assert type(getattr(database, attribute)).__name__ == FACADE_SURFACE[attribute][0]


@pytest.mark.parametrize("attribute", FROZEN_FACADE_ATTRIBUTES)
def test_facade_public_surface_is_unchanged(database: Database, attribute: str) -> None:
    """Each facade exposes the same public callables, with the same kind and signature."""
    assert (
        FacadeSurfaceReader.lines_of(getattr(database, attribute)) == FACADE_SURFACE[attribute][1]
    )


def _forbidden_imports(source: str) -> list[str]:
    """The imports of ``source`` that reach the app / worker packages or climb out of shared_libs."""
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_ROOTS]
        elif isinstance(node, ast.ImportFrom):
            if node.level > MAX_RELATIVE_LEVEL:
                offenders.append("." * node.level + (node.module or ""))
            elif node.level == 0 and (node.module or "").split(".")[0] in FORBIDDEN_ROOTS:
                offenders.append(node.module or "")
    return offenders


def test_import_scan_flags_app_and_worker_imports() -> None:
    """The scanner itself catches an app/worker import, a plain import and an escaping relative one."""
    source = "from backend.routers import x\nimport worker.core\nfrom .... import y\nimport uuid\n"
    assert _forbidden_imports(source) == ["backend.routers", "worker.core", "...."]


def test_facade_modules_are_discovered() -> None:
    """The scan covers the facade package (a moved folder would otherwise pass vacuously)."""
    assert len(list(FACADES_DIR.rglob("*.py"))) > 40


def test_no_facade_module_imports_the_app_or_worker_packages() -> None:
    """The data-layer facades depend on shared code only, never on the app or the worker."""
    offenders = {
        str(path.relative_to(FACADES_DIR)): found
        for path in sorted(FACADES_DIR.rglob("*.py"))
        if (found := _forbidden_imports(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}
