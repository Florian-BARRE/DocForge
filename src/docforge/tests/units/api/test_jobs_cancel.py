"""POST /jobs/{id}/cancel — the job-control endpoint (Phase 2 D).

Three surfaces, all serviceless (CONTEXT.database mocked, decisions computed before any mutation):
  * JobCancellationHelpers.decide — the pure state machine (queued→terminate, running→request/force,
    terminal→409) proven in isolation.
  * cancel_job — per-state orchestration: a queued job is force-terminated now, a running job is
    flagged cooperatively (force=false) or force-terminated (force=true), a finished job is 409, and
    the collection-scope gate fires (403) BEFORE any mutation while an unknown id is 404.

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registers app/ on sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


def _principal(*, permissions):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="user-1")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _scoped(collection_id: str):
    return _principal(
        permissions={"capabilities": ["read", "write"], "collections": [collection_id]}
    )


def _full():
    return _principal(permissions=None)


def _job(collection_id: str, status: str):
    """A minimal job row carrying the fields the cancel route reads (status + collection scope)."""
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    return SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=uuid.UUID(collection_id),
        status=JobStatus(status),
    )


def _wire(monkeypatch, *, job):
    """Point CONTEXT.database.jobs at get + the two mutation seams; return them for assertions."""
    from backend.context import CONTEXT  # noqa: PLC0415

    request_cancel = AsyncMock(return_value=job)
    force_terminate = AsyncMock(return_value=job)
    jobs = SimpleNamespace(
        get=AsyncMock(return_value=job),
        request_cancel=request_cancel,
        force_terminate=force_terminate,
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)
    monkeypatch.setattr(
        CONTEXT, "logger", SimpleNamespace(info=lambda *a, **k: None), raising=False
    )
    return request_cancel, force_terminate


# ── JobCancellationHelpers.decide — the pure state machine ───────────────────────────────────────


def test_decide_pending_is_terminate(fastapi_app) -> None:
    from backend.routers.jobs.helpers import CancelAction, JobCancellationHelpers  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    assert JobCancellationHelpers.decide(JobStatus.PENDING, force=False) == CancelAction.TERMINATE
    assert JobCancellationHelpers.decide(JobStatus.PENDING, force=True) == CancelAction.TERMINATE


def test_decide_running_is_request_or_force(fastapi_app) -> None:
    from backend.routers.jobs.helpers import CancelAction, JobCancellationHelpers  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    assert JobCancellationHelpers.decide(JobStatus.RUNNING, force=False) == CancelAction.REQUEST
    assert JobCancellationHelpers.decide(JobStatus.RUNNING, force=True) == CancelAction.FORCE


def test_decide_terminal_states_are_already_terminal(fastapi_app) -> None:
    from backend.routers.jobs.helpers import CancelAction, JobCancellationHelpers  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    for terminal in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
        assert JobCancellationHelpers.decide(terminal, force=False) == CancelAction.ALREADY_TERMINAL


# ── cancel_job — per-state orchestration ─────────────────────────────────────────────────────────


async def test_cancel_pending_terminates_now(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    job = _job(COLL_A, "pending")
    request_cancel, force_terminate = _wire(monkeypatch, job=job)

    result = await cancel_job(job_id=job.id, force=False, principal=_scoped(COLL_A))

    # A queued job is terminated immediately (the worker skips it at dequeue); no cooperative flag.
    force_terminate.assert_awaited_once()
    request_cancel.assert_not_awaited()
    assert result.status == "cancelled"
    assert result.outcome == "cancelled"
    assert result.cancel_requested is False


async def test_cancel_running_requests_cooperative_stop(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    job = _job(COLL_A, "running")
    request_cancel, force_terminate = _wire(monkeypatch, job=job)

    result = await cancel_job(job_id=job.id, force=False, principal=_scoped(COLL_A))

    # A running job is only FLAGGED (still running until it stops at a boundary); never force-killed.
    request_cancel.assert_awaited_once_with(job.id)
    force_terminate.assert_not_awaited()
    assert result.status == "running"
    assert result.outcome == "cancellation_requested"
    assert result.cancel_requested is True


async def test_cancel_running_force_terminates_now(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    job = _job(COLL_A, "running")
    request_cancel, force_terminate = _wire(monkeypatch, job=job)

    result = await cancel_job(job_id=job.id, force=True, principal=_scoped(COLL_A))

    # force=true immediately terminates a wedged running job (shares the reaper's transition).
    force_terminate.assert_awaited_once()
    request_cancel.assert_not_awaited()
    assert result.status == "cancelled"
    assert result.outcome == "cancelled"


async def test_cancel_already_terminal_is_409_before_any_mutation(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    job = _job(COLL_A, "done")
    request_cancel, force_terminate = _wire(monkeypatch, job=job)

    with pytest.raises(HTTPException) as exc:
        await cancel_job(job_id=job.id, force=False, principal=_scoped(COLL_A))

    assert exc.value.status_code == 409
    request_cancel.assert_not_awaited()
    force_terminate.assert_not_awaited()


async def test_cancel_unknown_job_is_404(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    jobs = SimpleNamespace(
        get=AsyncMock(return_value=None),
        request_cancel=AsyncMock(),
        force_terminate=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)

    with pytest.raises(HTTPException) as exc:
        await cancel_job(job_id=uuid.uuid4(), force=False, principal=_full())

    assert exc.value.status_code == 404
    jobs.request_cancel.assert_not_awaited()
    jobs.force_terminate.assert_not_awaited()


async def test_cancel_cross_tenant_is_403_before_any_mutation(fastapi_app, monkeypatch) -> None:
    from backend.routers.jobs.router import cancel_job  # noqa: PLC0415

    job = _job(COLL_B, "running")
    request_cancel, force_terminate = _wire(monkeypatch, job=job)

    with pytest.raises(HTTPException) as exc:
        await cancel_job(job_id=job.id, force=False, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # The scope gate fires before any state mutation.
    request_cancel.assert_not_awaited()
    force_terminate.assert_not_awaited()
