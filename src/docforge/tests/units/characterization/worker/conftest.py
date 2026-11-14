# ====== Code Summary ======
# Fixtures of the worker characterization suite. ``jobs.core`` / ``jobs.replay`` / ``jobs.cancellation``
# import ``from backend.context import CONTEXT`` (the WORKER's own backend.context), but the API tests of
# the same pytest session may already have registered ``sys.modules["backend"]`` as the APP's backend
# package (both apps define a top-level ``backend``). Same remedy as tests/units/worker/conftest.py: a
# throwaway ``backend.context`` satisfies the one-time import, sys.modules is restored right after, and
# every test then monkeypatches the modules' own ``CONTEXT`` name (see characterization_ingest_harness).

# ====== Standard Library Imports ======
import sys
import types

# ====== Third-Party Library Imports ======
import pytest


def _import_jobs_package():
    """Import the worker's flat ``jobs`` package (``jobs.core`` and every sibling it pulls in)."""
    import jobs  # noqa: PLC0415
    import jobs.core  # noqa: F401, PLC0415

    return jobs


def _import_with_fake_backend():
    saved = {key: sys.modules.get(key) for key in ("backend", "backend.context")}
    fake_backend = types.ModuleType("backend")
    fake_backend.__path__ = []
    fake_context_module = types.ModuleType("backend.context")
    fake_context_module.CONTEXT = types.SimpleNamespace()
    sys.modules["backend"] = fake_backend
    sys.modules["backend.context"] = fake_context_module
    try:
        return _import_jobs_package()
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


@pytest.fixture(scope="session")
def worker_jobs_package():
    """The worker's ``jobs`` package, imported once for the session (under a fake backend.context)."""
    if "jobs.core" in sys.modules:
        return sys.modules["jobs"]
    return _import_with_fake_backend()


@pytest.fixture
def jobs_core(worker_jobs_package):
    return sys.modules["jobs.core"]


@pytest.fixture
def jobs_replay(worker_jobs_package):
    return sys.modules["jobs.replay"]


@pytest.fixture
def jobs_cancellation(worker_jobs_package):
    return sys.modules["jobs.cancellation"]


@pytest.fixture
def load_worker_app(monkeypatch, worker_jobs_package):
    """Factory: execute the real worker/backend/app.py under the default (or overridden) config."""
    from characterization_worker_app_loader import WorkerAppLoader  # noqa: PLC0415

    def _load(**overrides):
        return WorkerAppLoader.load_worker_app(monkeypatch, worker_jobs_package, **overrides)

    return _load
