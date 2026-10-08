"""rebuild_collection_index — the arq task orchestrating an index rebuild over its PRE-CREATED job row.

Serviceless: every facade on the worker CONTEXT is an AsyncMock recording into ONE shared call log, so
the tests assert the step ORDER (wait → copy+swap → filter + meta-vector backfills → reconcile → done),
that a failure fails the job and skips every later step, that a residual missing vector fails the job
as ``rebuild_incomplete``, and that a terminal row at dequeue is skipped without touching the index.
The Qdrant copy/swap mechanics themselves are covered in test_rebuild_index_store.py.
"""

# ====== Standard Library Imports ======
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.services.db.facades.index_rebuild_payloads import (
    RebuildCancelledError,
    RebuildReconcileResult,
    StoreCopyResult,
)
from shared_libs.services.db.postgresql.tables import JobStatus


def _recorder(
    log: list[str], name: str, *, result: object = None, error: Exception | None = None
) -> AsyncMock:
    """An AsyncMock that appends ``name`` to the shared call log, then returns or raises."""

    async def _call(*args: object, **kwargs: object) -> object:
        log.append(name)
        if error is not None:
            raise error
        return result

    return AsyncMock(side_effect=_call)


def _context(
    log: list[str],
    *,
    existing_status: JobStatus = JobStatus.PENDING,
    copy_error: Exception | None = None,
    missing: list[str] | None = None,
) -> SimpleNamespace:
    """A worker CONTEXT whose rebuild facades all record into ``log``."""
    copy = StoreCopyResult(physical="col_x_r1", copied_points=7, document_ids={"d1", "d2"})
    reconciled = RebuildReconcileResult(missing_vectors=missing or [], needs_reindex=bool(missing))
    store_rebuild = _recorder(log, "copy_swap", result=copy, error=copy_error)
    return SimpleNamespace(
        worker_id="worker-1",
        logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None),
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_REBUILD_INDEX_WAIT_SECONDS=30.0, WORKER_REBUILD_INDEX_BATCH_SIZE=64
        ),
        database=SimpleNamespace(
            jobs=SimpleNamespace(
                get=AsyncMock(
                    return_value=SimpleNamespace(status=existing_status, cancel_requested=False)
                ),
                force_terminate=_recorder(log, "force_terminate"),
                mark_running=_recorder(log, "mark_running"),
                set_progress=AsyncMock(),
                mark_done=_recorder(log, "mark_done"),
                mark_failed=_recorder(log, "mark_failed"),
            ),
            index_rebuild=SimpleNamespace(
                wait_for_idle=_recorder(log, "wait_for_idle"),
                reconcile=_recorder(log, "reconcile", result=reconciled),
            ),
            store_rebuild=SimpleNamespace(rebuild=store_rebuild),
            filters=SimpleNamespace(
                backfill_collection_filter_payloads=_recorder(log, "filter_backfill")
            ),
            meta_vectors=SimpleNamespace(
                backfill_collection_meta_vectors=_recorder(log, "meta_backfill")
            ),
        ),
    )


@pytest.fixture
def jobs_rebuild(worker_jobs_modules):
    """The jobs.rebuild_index module (imported under the fake backend.context)."""
    import jobs.rebuild_index as module  # noqa: PLC0415

    return module


async def test_steps_run_in_order_and_complete_the_job(jobs_rebuild, monkeypatch) -> None:
    log: list[str] = []
    context = _context(log)
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)
    collection_id, job_id = uuid.uuid4(), uuid.uuid4()

    summary = await jobs_rebuild.rebuild_collection_index(
        {"job_try": 1}, str(collection_id), str(job_id)
    )

    # Wait before any Qdrant work; both backfills strictly AFTER the swap; reconcile last.
    assert log == [
        "mark_running",
        "wait_for_idle",
        "copy_swap",
        "filter_backfill",
        "meta_backfill",
        "reconcile",
        "mark_done",
    ]
    assert summary == {
        "physical": "col_x_r1",
        "copied_points": 7,
        "first_rebuild": False,
        "missing_vectors": [],
        "reingest_required_fields": [],
        "needs_reindex": False,
        "dense_space_changed": False,
        "reencoded_sparse_points": 0,
    }
    database = context.database
    wait = database.index_rebuild.wait_for_idle.await_args
    assert wait.args == (collection_id, job_id, 30.0) and wait.kwargs["should_abort"]
    rebuild = database.store_rebuild.rebuild.await_args
    assert rebuild.args == (collection_id, 64) and rebuild.kwargs["should_abort"]
    # The copy summary (seen document ids, carried vectors) feeds the reconciliation.
    reconcile = database.index_rebuild.reconcile.await_args.args
    assert reconcile[0] == collection_id and reconcile[1].document_ids == {"d1", "d2"}


async def test_copy_failure_fails_job_and_skips_backfills(jobs_rebuild, monkeypatch) -> None:
    log: list[str] = []
    context = _context(log, copy_error=RuntimeError("qdrant down"))
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    with pytest.raises(RuntimeError, match="qdrant down"):
        await jobs_rebuild.rebuild_collection_index({}, str(uuid.uuid4()), str(uuid.uuid4()))

    assert log == ["mark_running", "wait_for_idle", "copy_swap", "mark_failed"]
    assert context.database.jobs.mark_failed.await_args.kwargs["error_type"] == "RuntimeError"


async def test_wait_timeout_fails_before_any_qdrant_work(jobs_rebuild, monkeypatch) -> None:
    log: list[str] = []
    context = _context(log)
    context.database.index_rebuild.wait_for_idle = _recorder(
        log, "wait_for_idle", error=TimeoutError("still busy")
    )
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    with pytest.raises(TimeoutError):
        await jobs_rebuild.rebuild_collection_index({}, str(uuid.uuid4()), str(uuid.uuid4()))

    assert log == ["mark_running", "wait_for_idle", "mark_failed"]


async def test_residual_missing_vectors_fail_as_incomplete(jobs_rebuild, monkeypatch) -> None:
    log: list[str] = []
    context = _context(log, missing=["meta_topic_dense"])
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    summary = await jobs_rebuild.rebuild_collection_index({}, str(uuid.uuid4()), str(uuid.uuid4()))

    assert summary["missing_vectors"] == ["meta_topic_dense"]
    assert log[-1] == "mark_failed"
    assert "mark_done" not in log
    assert context.database.jobs.mark_failed.await_args.kwargs["error_type"] == "rebuild_incomplete"


@pytest.mark.parametrize("status", sorted(JobStatus.terminal(), key=str))
async def test_terminal_row_at_dequeue_is_skipped(jobs_rebuild, monkeypatch, status) -> None:
    log: list[str] = []
    context = _context(log, existing_status=status)
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    summary = await jobs_rebuild.rebuild_collection_index({}, str(uuid.uuid4()), str(uuid.uuid4()))

    # The admission lock is gone once the row is terminal: never copy a store ingests may be writing.
    assert summary == {"skipped": True}
    assert log == []


async def test_pre_swap_cancel_marks_cancelled_not_failed(jobs_rebuild, monkeypatch) -> None:
    log: list[str] = []
    context = _context(log, copy_error=RebuildCancelledError("rebuild cancelled before the swap"))
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    summary = await jobs_rebuild.rebuild_collection_index({}, str(uuid.uuid4()), str(uuid.uuid4()))

    # The facade already dropped the temp; the row ends CANCELLED, nothing after the copy runs.
    assert summary == {"cancelled": True}
    assert log == ["mark_running", "wait_for_idle", "copy_swap", "force_terminate"]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (None, True),
        (SimpleNamespace(status=JobStatus.RUNNING, cancel_requested=False), False),
        (SimpleNamespace(status=JobStatus.RUNNING, cancel_requested=True), True),
        (SimpleNamespace(status=JobStatus.FAILED, cancel_requested=False), True),
    ],
)
async def test_abort_probe_reads_the_own_row(jobs_rebuild, monkeypatch, row, expected) -> None:
    context = _context([])
    context.database.jobs.get = AsyncMock(return_value=row)
    monkeypatch.setattr(jobs_rebuild, "CONTEXT", context)

    # A reaped (terminal) row on a live worker aborts exactly like a cooperative cancel.
    assert await jobs_rebuild._abort_probe(uuid.uuid4())() is expected
