# ====== Code Summary ======
# jobs.core / jobs.backfill import `from backend.context import CONTEXT` (the WORKER's own
# backend.context), but the API tests in the SAME pytest session may already have registered
# `sys.modules["backend"]` as the APP's backend package (tests/units/api/conftest.py). Both apps
# define a top-level `backend` package, so importing worker/'s real backend.context here would
# either collide with, or be shadowed by, the app's. Since `jobs` (worker/backend/libs/jobs) is
# already flat-importable (worker/backend/libs is on sys.path — see the root conftest), the ONLY
# missing piece is a throwaway `backend.context.CONTEXT` to satisfy the one-time import; every
# test then monkeypatches the module's own `CONTEXT` name directly (see test_jobs_core.py /
# test_jobs_backfill.py), so the throwaway object's identity never matters again. sys.modules is
# restored immediately after the one-time import so later API tests still get the REAL app backend.

# ====== Standard Library Imports ======
import sys
import types

# ====== Third-Party Library Imports ======
import pytest


def _import_worker_jobs_modules():
    """Import jobs.core + jobs.backfill under a throwaway fake backend.context (one-time)."""
    import jobs.backfill as backfill_module  # noqa: PLC0415
    import jobs.core as core_module  # noqa: PLC0415

    return core_module, backfill_module


def _import_with_fake_backend():
    saved = {key: sys.modules.get(key) for key in ("backend", "backend.context")}
    fake_backend = types.ModuleType("backend")
    fake_backend.__path__ = []
    fake_context_module = types.ModuleType("backend.context")
    fake_context_module.CONTEXT = types.SimpleNamespace()
    sys.modules["backend"] = fake_backend
    sys.modules["backend.context"] = fake_context_module
    try:
        return _import_worker_jobs_modules()
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


@pytest.fixture(scope="session")
def worker_jobs_modules():
    """(jobs.core, jobs.backfill) module objects, imported exactly once for the session."""
    if "jobs.core" in sys.modules and "jobs.backfill" in sys.modules:
        return _import_worker_jobs_modules()
    return _import_with_fake_backend()


@pytest.fixture
def jobs_core(worker_jobs_modules):
    return worker_jobs_modules[0]


@pytest.fixture
def jobs_backfill(worker_jobs_modules):
    return worker_jobs_modules[1]
