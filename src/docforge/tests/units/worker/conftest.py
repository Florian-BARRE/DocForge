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
    """Import jobs.core + backfill + transfer + preview + metadata_sync under a fake backend.context."""
    import jobs.backfill as backfill_module  # noqa: PLC0415
    import jobs.core as core_module  # noqa: PLC0415
    import jobs.metadata_sync as metadata_sync_module  # noqa: PLC0415
    import jobs.preview as preview_module  # noqa: PLC0415
    import jobs.rebuild_index  # noqa: F401, PLC0415 — imported under the fake backend.context too
    import jobs.transfer as transfer_module  # noqa: PLC0415

    return core_module, backfill_module, transfer_module, preview_module, metadata_sync_module


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
    """(jobs.core, jobs.backfill, jobs.transfer, jobs.preview) modules, imported once for the session."""
    if all(
        name in sys.modules
        for name in (
            "jobs.core",
            "jobs.backfill",
            "jobs.transfer",
            "jobs.preview",
            "jobs.metadata_sync",
            "jobs.rebuild_index",
        )
    ):
        return _import_worker_jobs_modules()
    return _import_with_fake_backend()


@pytest.fixture
def jobs_core(worker_jobs_modules):
    return worker_jobs_modules[0]


@pytest.fixture
def jobs_backfill(worker_jobs_modules):
    return worker_jobs_modules[1]


@pytest.fixture
def jobs_transfer(worker_jobs_modules):
    return worker_jobs_modules[2]


@pytest.fixture
def jobs_preview(worker_jobs_modules):
    return worker_jobs_modules[3]


@pytest.fixture
def jobs_metadata_sync(worker_jobs_modules):
    return worker_jobs_modules[4]


@pytest.fixture(autouse=True)
def _no_rebuild_guard(monkeypatch):
    """Neutralise the ingest-admission rebuild guard (its SQL needs a real session; mocks are sync)."""
    from shared_libs.services.db.facades import rebuild_guard  # noqa: PLC0415

    monkeypatch.setattr(rebuild_guard.RebuildGuard, "assert_no_rebuild", staticmethod(_async_noop))


async def _async_noop(*args, **kwargs) -> None:
    """Awaitable no-op stand-in."""
    return None
