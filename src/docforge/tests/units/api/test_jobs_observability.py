"""SRE observability on the jobs router — triage filters, failure breakdown, new-failures, trends.

Guards the V1 observability surface added for the SRE persona:
  * GET /jobs threads the triage facets (stage / error class / id search / date range / sort) to the
    data layer, and a job carries a ``duration_seconds``.
  * GET /jobs/failures/breakdown rolls failures up three ways (cause / stage / collection), gated
    fleet-vs-scoped exactly like the listing.
  * GET /jobs/failures/new counts failures past a cursor (optionally returning ids).
  * GET /jobs/timeseries reconstructs contiguous hourly buckets (done/failed/arrivals/backlog).

CONTEXT.database is mocked; ``from backend...`` imports are deferred until the ``fastapi_app`` fixture
has registered app/ on sys.path (see tests/units/api/conftest.py).
"""

import uuid
from datetime import UTC, datetime, timedelta
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
    return _principal(permissions={"capabilities": ["read"], "collections": [collection_id]})


def _full():
    return _principal(permissions=None)


# ── GET /jobs — triage filters + sort thread to the data layer ───────────────────────────────────


async def test_list_jobs_threads_triage_filters_and_sort(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    list_page = AsyncMock(return_value=[])
    count = AsyncMock(return_value=3)
    jobs = SimpleNamespace(list_jobs_with_names=list_page, count_jobs=count)
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    after = datetime(2026, 9, 1, tzinfo=UTC)
    before = datetime(2026, 9, 10, tzinfo=UTC)
    await list_jobs(
        collection_id=uuid.UUID(COLL_A),
        status=None,
        stage="embed",
        error_type="TimeoutError",
        search="9a8b",
        created_after=after,
        created_before=before,
        sort="duration",
        order="oldest",
        limit=25,
        offset=0,
        principal=_full(),
    )

    # Every triage facet + the duration sort (ASC via order=oldest) reaches the facade verbatim.
    list_page.assert_awaited_once_with(
        collection_id=uuid.UUID(COLL_A),
        statuses=None,
        limit=25,
        offset=0,
        newest_first=False,
        sort_by="duration",
        stage="embed",
        error_type="TimeoutError",
        search="9a8b",
        created_after=after,
        created_before=before,
    )
    count.assert_awaited_once_with(
        uuid.UUID(COLL_A),
        None,
        stage="embed",
        error_type="TimeoutError",
        search="9a8b",
        created_after=after,
        created_before=before,
    )


def test_job_status_duration_seconds() -> None:
    """from_row computes duration: terminal = finished−started, running = elapsed, queued = None."""
    from backend.routers.jobs.models import JobStatus  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import (
        JobStatus as JobStatusEnum,  # noqa: PLC0415
    )

    started = datetime.now(UTC) - timedelta(seconds=120)

    def _row(**over):
        base = dict(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            collection_id=uuid.uuid4(),
            status=JobStatusEnum.DONE,
            cancel_requested=False,
            progress=100,
            current_stage=None,
            error=None,
            attempt=1,
            started_at=started,
            finished_at=started + timedelta(seconds=90),
            updated_at=datetime.now(UTC),
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
        base.update(over)
        return SimpleNamespace(**base)

    # Terminal: the exact span.
    done = JobStatus.from_row(_row())
    assert done.duration_seconds == pytest.approx(90.0, abs=0.5)

    # Running: elapsed so far (≈120s), no finish yet.
    running = JobStatus.from_row(_row(status=JobStatusEnum.RUNNING, finished_at=None, progress=40))
    assert running.duration_seconds == pytest.approx(120.0, abs=2.0)

    # Queued: never started → no duration.
    queued = JobStatus.from_row(
        _row(status=JobStatusEnum.PENDING, started_at=None, finished_at=None, progress=0)
    )
    assert queued.duration_seconds is None


# ── GET /jobs/failures/breakdown ─────────────────────────────────────────────────────────────────


async def test_failure_breakdown_fleetwide_denied_for_scoped_key(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import failure_breakdown  # noqa: PLC0415

    probe = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(failure_breakdown=probe))
    )

    with pytest.raises(HTTPException) as exc:
        await failure_breakdown(collection_id=None, window_hours=24, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    probe.assert_not_awaited()


async def test_failure_breakdown_builds_panel_with_unknown_labels(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import failure_breakdown  # noqa: PLC0415
    from shared_libs.services.db.postgresql.apis.job_api import FailureAggregates  # noqa: PLC0415

    coll = uuid.UUID(COLL_A)
    aggregates = FailureAggregates(
        total=5,
        by_error_type=[("TimeoutError", 3), (None, 2)],  # a null class surfaces as "unknown"
        by_stage=[("embed", 4), ("parse", 1)],
        by_collection=[(coll, "Docs", 5)],
    )
    probe = AsyncMock(return_value=aggregates)
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(failure_breakdown=probe))
    )

    result = await failure_breakdown(collection_id=coll, window_hours=48, principal=_full())

    assert result.total_failed == 5
    assert result.window_hours == 48
    assert result.collection_id == COLL_A
    assert [(b.label, b.count) for b in result.by_error_type] == [
        ("TimeoutError", 3),
        ("unknown", 2),
    ]
    assert [(b.label, b.count) for b in result.by_stage] == [("embed", 4), ("parse", 1)]
    assert result.by_collection[0].collection_id == COLL_A
    assert result.by_collection[0].collection_name == "Docs"
    # The window start is derived and passed to the data layer.
    (passed_since, passed_coll) = probe.await_args.args
    assert passed_coll == coll
    assert isinstance(passed_since, datetime)


# ── GET /jobs/failures/new ───────────────────────────────────────────────────────────────────────


async def test_new_failures_count_only_skips_id_read(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import new_failures  # noqa: PLC0415

    latest = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    count_probe = AsyncMock(return_value=(4, latest))
    ids_probe = AsyncMock(return_value=[])
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            jobs=SimpleNamespace(count_failed_since=count_probe, list_failed_since=ids_probe)
        ),
    )

    since = datetime(2026, 9, 11, tzinfo=UTC)
    result = await new_failures(
        since=since, collection_id=None, include_ids=False, limit=50, principal=_full()
    )

    assert result.count == 4
    assert result.latest_failed_at == latest
    assert result.job_ids == []
    # include_ids=False → the id read is never issued.
    ids_probe.assert_not_awaited()
    count_probe.assert_awaited_once_with(since, None)


async def test_new_failures_with_ids(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import new_failures  # noqa: PLC0415

    ids = [uuid.UUID(COLL_A), uuid.UUID(COLL_B)]
    count_probe = AsyncMock(return_value=(2, datetime.now(UTC)))
    ids_probe = AsyncMock(return_value=ids)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            jobs=SimpleNamespace(count_failed_since=count_probe, list_failed_since=ids_probe)
        ),
    )

    since = datetime(2026, 9, 11, tzinfo=UTC)
    result = await new_failures(
        since=since, collection_id=None, include_ids=True, limit=10, principal=_full()
    )

    assert result.count == 2
    assert result.job_ids == [str(i) for i in ids]
    ids_probe.assert_awaited_once_with(since, None, 10)


async def test_new_failures_fleetwide_denied_for_scoped_key(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import new_failures  # noqa: PLC0415

    count_probe = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(count_failed_since=count_probe))
    )

    with pytest.raises(HTTPException) as exc:
        await new_failures(
            since=datetime.now(UTC),
            collection_id=None,
            include_ids=False,
            limit=50,
            principal=_scoped(COLL_A),
        )

    assert exc.value.status_code == 403
    count_probe.assert_not_awaited()


# ── GET /jobs/timeseries ─────────────────────────────────────────────────────────────────────────


async def test_timeseries_reconstructs_contiguous_buckets(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import job_timeseries  # noqa: PLC0415
    from shared_libs.services.db.postgresql.apis.job_api import (
        TimeseriesAggregates,  # noqa: PLC0415
    )
    from shared_libs.services.db.postgresql.tables import (
        JobStatus as JobStatusEnum,  # noqa: PLC0415
    )

    # Two hours of activity with a pre-window baseline of 1 queued job.
    now = datetime.now(UTC).replace(minute=30, second=0, microsecond=0)
    h0 = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    h1 = now.replace(minute=0, second=0, microsecond=0)
    aggregates = TimeseriesAggregates(
        baseline=1,
        arrivals=[(h0, 2), (h1, 1)],
        completions=[(h0, JobStatusEnum.DONE, 1), (h1, JobStatusEnum.FAILED, 1)],
    )
    probe = AsyncMock(return_value=aggregates)
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(job_timeseries=probe))
    )

    result = await job_timeseries(collection_id=None, window_hours=2, principal=_full())

    assert result.bucket_seconds == 3600
    assert result.window_hours == 2
    # Contiguous hourly buckets (gap-free) over the window, oldest first.
    assert len(result.buckets) >= 2
    by_start = {b.bucket_start: b for b in result.buckets}
    # h0: +2 arrivals, 1 done → backlog = baseline(1) + 2 - 1 = 2.
    assert by_start[h0].created == 2
    assert by_start[h0].done == 1
    assert by_start[h0].backlog == 2
    # h1: +1 arrival, 1 failed → backlog = 2 + 1 - 1 = 2.
    assert by_start[h1].created == 1
    assert by_start[h1].failed == 1
    assert by_start[h1].backlog == 2


async def test_timeseries_fleetwide_denied_for_scoped_key(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import job_timeseries  # noqa: PLC0415

    probe = AsyncMock()
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(jobs=SimpleNamespace(job_timeseries=probe))
    )

    with pytest.raises(HTTPException) as exc:
        await job_timeseries(collection_id=None, window_hours=24, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    probe.assert_not_awaited()
