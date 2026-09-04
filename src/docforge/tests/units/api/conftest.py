# ====== Code Summary ======
# Boots the REAL FastAPI app (app/entrypoint.py) once per session, exactly like uvicorn would:
# app/ inserted at the front of sys.path so ``from config import RUNTIME_CONFIG`` and
# ``from backend import ...`` resolve relative to the app, then ``entrypoint`` imported so its
# module-level ``app = _build_app()`` runs. Stores connect LAZILY (Database/QueueClient just hold
# their connection settings at construction), so the app boots and serves its design/stage
# surfaces with no compose stack running — routes that DO need a store (collections list,
# documents upload) are exercised only in tests/live.

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient

# tests/units/api/conftest.py -> parents[3] is the docforge repo root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "app"


@pytest.fixture(scope="session")
def fastapi_app():
    """Import and return the real FastAPI app instance, booted from app/entrypoint.py."""
    app_dir_str = str(APP_DIR)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)
    from entrypoint import app  # noqa: PLC0415 — import deferred until the path is registered

    return app


@pytest.fixture
def client(fastapi_app) -> TestClient:
    """A TestClient bound to the real app, one per test (cheap: no network I/O at construction)."""
    return TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def _auth_off_by_default(fastapi_app, monkeypatch):
    """Force auth OFF for the whole unit suite, independent of the ambient services/.env.

    The app is auth-off by design in dev + tests; the authN middleware reads
    ``RUNTIME_CONFIG.AUTH_ENABLED`` per request, so a local ``.env`` that enables auth (for a live
    stack) would otherwise 401 every route test. Tests that DO exercise auth-on monkeypatch the flag
    back to True themselves (this runs first; their override wins and reverts cleanly).
    """
    from config import RUNTIME_CONFIG  # noqa: PLC0415 — deferred until app/ is on sys.path

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False)
    # Keep the "all-mocked" unit run HERMETIC: AuditMiddleware records one audit_log row per mutating
    # /api/v1 request via the UNMOCKED CONTEXT.database.audit.record, so with AUDIT_ENABLED at its
    # default (True) every mutating route test wrote a real row into (and leaked a connection to) the
    # dev Postgres whenever the stack happened to be up — invisibly (the write is swallowed when it is
    # down). Off here regardless of the ambient .env; test_audit.py flips it back on with mocks to
    # cover the audit path itself (its override runs after this and wins, reverting cleanly).
    monkeypatch.setattr(RUNTIME_CONFIG, "AUDIT_ENABLED", False)
