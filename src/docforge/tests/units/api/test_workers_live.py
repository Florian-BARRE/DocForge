"""GET /jobs/workers/live tenant isolation + crashed-worker pruning.

The fleet-wide workers/live endpoint carries no ``collection_id`` in the path, so a naive READ gate
would leak EVERY worker's running-job identifiers (job/document/collection ids) to any scoped key.
These tests prove:
  * WorkersLiveHelpers.assemble strips jobs outside the caller's allowed collections (None = all),
    while still surfacing worker liveness for every worker.
  * live_workers derives the allowed set from the principal (full access = all, scoped = its own),
    and prunes stale heartbeats on the DB clock before assembling the view.

Store access is mocked via CONTEXT.database; ``from backend...`` imports are deferred until the
``fastapi_app`` fixture has registered app/ on sys.path (see tests/units/api/conftest.py).
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

# Two stable collection ids — the "owned" (A) and the "foreign" (B) tenant.
COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


def _principal(*, permissions):
    """Build an AuthPrincipal directly (full access iff permissions is None)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="user-1")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _scoped(collection_id: str):
    """A scoped key granting read on exactly one collection."""
    return _principal(permissions={"capabilities": ["read"], "collections": [collection_id]})


def _wildcard():
    """A scoped key whose collection scope is the wildcard (every collection)."""
    return _principal(permissions={"capabilities": ["read"], "collections": ["*"]})


def _full():
    """A full-access (root / NULL-permission) principal."""
    return _principal(permissions=None)


def _running_job(collection_id: str, worker_id: str):
    """A stand-in RUNNING job as JobWithNames — the job row plus its joined display names."""
    job = SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        collection_id=uuid.UUID(collection_id),
        worker_id=worker_id,
        status=SimpleNamespace(value="running"),
        cancel_requested=False,
        progress=50,
        current_stage="embed",
        error=None,
        attempt=1,
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0,
        items_done=None,
        items_total=None,
        failed_node_id=None,
        failed_node_kind=None,
        failed_item_index=None,
        error_type=None,
    )
    return SimpleNamespace(job=job, document_filename="report.pdf", collection_name="my-collection")


def _heartbeat(worker_id: str, worker_name: str | None = None):
    """A fresh heartbeat row for one worker (worker_name defaults to the id when omitted)."""
    now = datetime.now(UTC)
    return SimpleNamespace(
        worker_id=worker_id, worker_name=worker_name or worker_id, last_seen=now, started_at=now
    )


# ── WorkersLiveHelpers.assemble — job scoping ────────────────────────────────────────────────────


def test_assemble_scoped_strips_foreign_jobs(fastapi_app) -> None:
    from backend.routers.jobs.helpers import WorkersLiveHelpers  # noqa: PLC0415

    heartbeats = [_heartbeat("w1")]
    running = [_running_job(COLL_A, "w1"), _running_job(COLL_B, "w1")]

    view = WorkersLiveHelpers.assemble(heartbeats, running, allowed_collections={COLL_A})

    worker = view.workers[0]
    # Only the owned-collection job is attached; busy reflects the filtered set.
    assert [job.collection_id for job in worker.jobs] == [COLL_A]
    assert worker.busy is True


def test_assemble_unrestricted_shows_every_job(fastapi_app) -> None:
    from backend.routers.jobs.helpers import WorkersLiveHelpers  # noqa: PLC0415

    heartbeats = [_heartbeat("w1")]
    running = [_running_job(COLL_A, "w1"), _running_job(COLL_B, "w1")]

    view = WorkersLiveHelpers.assemble(heartbeats, running, allowed_collections=None)

    assert {job.collection_id for job in view.workers[0].jobs} == {COLL_A, COLL_B}


def test_assemble_scoped_keeps_worker_liveness_with_no_visible_jobs(fastapi_app) -> None:
    """A worker running only foreign jobs still shows (infra liveness) — but with no job details."""
    from backend.routers.jobs.helpers import WorkersLiveHelpers  # noqa: PLC0415

    heartbeats = [_heartbeat("w1")]
    running = [_running_job(COLL_B, "w1")]

    view = WorkersLiveHelpers.assemble(heartbeats, running, allowed_collections={COLL_A})

    worker = view.workers[0]
    assert worker.alive is True
    assert worker.jobs == []
    assert worker.busy is False


# ── live_workers route — principal-derived scope + pruning ───────────────────────────────────────


def _wire_jobs(monkeypatch, *, running):
    """Point CONTEXT.database.jobs at prune/list mocks; return the prune mock for assertions."""
    from backend.context import CONTEXT  # noqa: PLC0415

    prune = AsyncMock(return_value=[])
    jobs = SimpleNamespace(
        prune_stale_heartbeats=prune,
        list_heartbeats=AsyncMock(return_value=[_heartbeat("w1")]),
        list_active_with_names=AsyncMock(return_value=running),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))
    return prune


async def test_live_workers_scoped_key_cannot_see_foreign_jobs(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415

    running = [_running_job(COLL_A, "w1"), _running_job(COLL_B, "w1")]
    _wire_jobs(monkeypatch, running=running)

    view = await live_workers(principal=_scoped(COLL_A))

    # The endpoint never surfaces the foreign collection's job (nor its ids) to a scoped key.
    all_collections = {job.collection_id for worker in view.workers for job in worker.jobs}
    assert all_collections == {COLL_A}


async def test_live_workers_full_access_sees_every_job(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415

    running = [_running_job(COLL_A, "w1"), _running_job(COLL_B, "w1")]
    _wire_jobs(monkeypatch, running=running)

    view = await live_workers(principal=_full())

    all_collections = {job.collection_id for worker in view.workers for job in worker.jobs}
    assert all_collections == {COLL_A, COLL_B}


async def test_live_workers_wildcard_key_sees_every_job(fastapi_app, monkeypatch) -> None:
    """A wildcard-scoped key ('*') is treated like full access for the fleet view."""
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415

    running = [_running_job(COLL_A, "w1"), _running_job(COLL_B, "w1")]
    _wire_jobs(monkeypatch, running=running)

    view = await live_workers(principal=_wildcard())

    all_collections = {job.collection_id for worker in view.workers for job in worker.jobs}
    assert all_collections == {COLL_A, COLL_B}


async def test_live_workers_prunes_stale_heartbeats_first(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    prune = _wire_jobs(monkeypatch, running=[])

    await live_workers(principal=_full())

    # Crashed workers are swept on the configured cutoff before the view is assembled.
    prune.assert_awaited_once_with(RUNTIME_CONFIG.WORKER_PRUNE_STALE_SECONDS)


# ── fail-closed authz contract ───────────────────────────────────────────────────────────────────


async def test_live_workers_malformed_scope_is_403_before_any_db_read(
    fastapi_app, monkeypatch
) -> None:
    """A corrupt permissions blob denies (403) at the in-memory scope step — no prune/read fires."""
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415

    prune = _wire_jobs(monkeypatch, running=[])
    # A non-full-access key whose blob fails KeyPermissions validation (extra='forbid' + missing keys).
    malformed = _principal(permissions={"bogus": True})

    with pytest.raises(HTTPException) as exc:
        await live_workers(principal=malformed)

    assert exc.value.status_code == 403
    # The deny fires BEFORE any DB touch — the crashed-worker sweep never runs for a rejected key.
    prune.assert_not_awaited()


async def test_live_workers_drops_a_job_with_no_collection_for_a_scoped_key(
    fastapi_app, monkeypatch
) -> None:
    """A running job whose collection_id is None is never leaked to a scoped key (str(None) ∉ scope)."""
    from backend.routers.jobs.router import live_workers  # noqa: PLC0415

    orphan = _running_job(COLL_A, "w1")
    orphan.job.collection_id = None
    _wire_jobs(monkeypatch, running=[orphan])

    view = await live_workers(principal=_scoped(COLL_A))

    # The unscoped/orphan job is dropped; the worker shows alive but with no visible jobs.
    assert all(worker.jobs == [] for worker in view.workers)
