# ====== Code Summary ======
# Root pytest bootstrap — registers the ``shared_libs`` package alias and the worker's
# backend/libs import root ONCE for the whole test session, mirroring the sys.path wiring each
# app's own config package performs at import time (see app/config/helpers.py and
# worker/config/helpers.py: RuntimePathHelpers.register_package_alias / add_to_python_path).
#
# Doing this exactly once here (rather than per test module, as the exploratory scratchpad
# scripts did) matters because shared_libs.pipelines.registry.NodeRegistry is PROCESS-GLOBAL
# state: importing a node package twice would be harmless (Python caches modules), but two
# independent module OBJECTS both claiming the name "shared_libs" would not be — so the alias
# must be installed before anything imports it, and only once.
#
# Only ``shared_libs`` + the worker's backend/libs are added at collection time. The app's own
# root (needed for ``from entrypoint import app``) is added lazily by the ``fastapi_app`` fixture
# in tests/units/api/conftest.py — importing it eagerly here would pull FastAPI/CORS/DB-client
# construction into every test run, including pure pipeline unit tests that never need it.

# ====== Standard Library Imports ======
import pathlib
import sys
import types

# The repository root (src/docforge/), independent of the process's cwd — pytest is
# expected to run from here, but nothing in this bootstrap relies on that.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SHARED_LIBS_DIR = REPO_ROOT / "shared" / "libs"
APP_DIR = REPO_ROOT / "app"
WORKER_DIR = REPO_ROOT / "worker"
WORKER_LIBS_DIR = WORKER_DIR / "backend" / "libs"


def _register_shared_libs_alias() -> None:
    """Expose shared/libs as the importable package ``shared_libs`` (idempotent)."""
    if "shared_libs" in sys.modules:
        return
    module = types.ModuleType("shared_libs")
    module.__path__ = [str(SHARED_LIBS_DIR)]
    sys.modules["shared_libs"] = module


def _add_worker_libs_to_path() -> None:
    """Expose worker/backend/libs's packages (runner, persistence, jobs) as top-level imports.

    Deliberately does NOT add the worker root itself: worker/backend/libs's modules only ever
    import ``shared_libs`` (verified by inspection), never the worker's own ``config``/``backend``
    packages — so this stays free of the app/worker namespace collision documented in
    agent-memory (both apps define top-level ``backend`` and ``config`` packages; only one of
    them may ever be registered per process).
    """
    path_str = str(WORKER_LIBS_DIR)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_register_shared_libs_alias()
_add_worker_libs_to_path()
