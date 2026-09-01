"""ingest_document — the best-effort filter/meta-vector sync hooks after index(): a hiccup in
EITHER hook must NOT fail an already-persisted ingestion (mark_done, never mark_failed, no
re-raise), and neither hook runs when the translated run produced no points. Database/S3/runner
are fully mocked through the module's own `CONTEXT` name (see conftest.py for why)."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _fake_database() -> SimpleNamespace:
    return SimpleNamespace(
        jobs=SimpleNamespace(
            get=AsyncMock(return_value=None),
            mark_running=AsyncMock(),
            mark_done=AsyncMock(),
            mark_failed=AsyncMock(),
            force_terminate=AsyncMock(),
            is_cancel_requested=AsyncMock(return_value=False),
        ),
        documents=SimpleNamespace(get=AsyncMock(), get_metadata=AsyncMock(return_value=[])),
        collections=SimpleNamespace(get=AsyncMock(), get_schema=AsyncMock(return_value=[])),
        ingestion=SimpleNamespace(
            store_blobs=AsyncMock(),
            save=AsyncMock(),
            index=AsyncMock(),
            mark_failed=AsyncMock(),
            mark_processing=AsyncMock(),
        ),
        filters=SimpleNamespace(sync_document_filter_payloads=AsyncMock()),
        meta_vectors=SimpleNamespace(sync_document_meta_vectors=AsyncMock()),
    )


class _FakeS3:
    bucket = "bucket"

    def client(self):
        @asynccontextmanager
        async def _cm():
            yield MagicMock()

        return _cm()


def _fake_context(database: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        database=database,
        s3=_FakeS3(),
        runner=SimpleNamespace(run=AsyncMock(return_value=(MagicMock(), MagicMock()))),
        worker_id="w1",
        job_timeout_seconds=30.0,
        RUNTIME_CONFIG=SimpleNamespace(
            WORKER_PREFLIGHT_ENABLED=True, WORKER_JOB_TIMEOUT_MAX_SECONDS=7200.0
        ),
        logger=MagicMock(),
    )


def _wire(jobs_core, monkeypatch, database: SimpleNamespace, points, job_timeout_seconds=None):
    """Patch CONTEXT + the module-level S3ObjectApi/RunTranslator seams for one run."""
    context = _fake_context(database)
    monkeypatch.setattr(jobs_core, "CONTEXT", context)
    monkeypatch.setattr(jobs_core.S3ObjectApi, "get", AsyncMock(return_value=b"raw-bytes"))
    # Blob normalization is covered on its own (tests/units/stages/test_blob_normalization.py);
    # these tests exercise the job lifecycle + sync hooks, so pass the stub blob through as-is.
    monkeypatch.setattr(jobs_core.BlobNormalizer, "normalize", lambda blob: dict(blob))

    document_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        collection_id=collection_id,
        filename="f.pdf",
        source_hash="hash",
    )
    collection = SimpleNamespace(
        id=collection_id,
        name="c",
        supported_formats=["pdf"],
        max_file_size_bytes=100,
        job_timeout_seconds=job_timeout_seconds,
        pipeline={"nodes": []},
    )
    database.documents.get = AsyncMock(return_value=document)
    database.collections.get = AsyncMock(return_value=collection)

    translated = SimpleNamespace(
        objects=[], blob_rows=[], payload=MagicMock(), points=points, dense_dim=4
    )
    monkeypatch.setattr(jobs_core.RunTranslator, "translate", MagicMock(return_value=translated))
    return document_id, context


async def test_filter_sync_failure_still_marks_job_done_not_failed(jobs_core, monkeypatch) -> None:
    database = _fake_database()
    database.filters.sync_document_filter_payloads = AsyncMock(side_effect=RuntimeError("boom"))
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.jobs.mark_done.assert_awaited_once()
    database.jobs.mark_failed.assert_not_awaited()
    database.meta_vectors.sync_document_meta_vectors.assert_awaited_once_with(document_id)


async def test_meta_vector_sync_failure_still_marks_job_done_not_failed(
    jobs_core, monkeypatch
) -> None:
    database = _fake_database()
    database.meta_vectors.sync_document_meta_vectors = AsyncMock(side_effect=RuntimeError("boom"))
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.jobs.mark_done.assert_awaited_once()
    database.jobs.mark_failed.assert_not_awaited()
    database.filters.sync_document_filter_payloads.assert_awaited_once_with(document_id)


async def test_no_points_skips_both_sync_hooks(jobs_core, monkeypatch) -> None:
    database = _fake_database()
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[])

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.filters.sync_document_filter_payloads.assert_not_awaited()
    database.meta_vectors.sync_document_meta_vectors.assert_not_awaited()
    database.ingestion.index.assert_not_awaited()
    database.jobs.mark_done.assert_awaited_once()


async def test_happy_path_calls_both_hooks_with_the_document_id(jobs_core, monkeypatch) -> None:
    database = _fake_database()
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.filters.sync_document_filter_payloads.assert_awaited_once_with(document_id)
    database.meta_vectors.sync_document_meta_vectors.assert_awaited_once_with(document_id)
    database.jobs.mark_done.assert_awaited_once()
    database.jobs.mark_failed.assert_not_awaited()


async def test_claim_transitions_the_document_to_processing(jobs_core, monkeypatch) -> None:
    """The worker flips the DOCUMENT PENDING → PROCESSING as it claims the job, so it no longer
    reads 'pending' for the whole run — mark_running only moves the JOB row."""
    database = _fake_database()
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.ingestion.mark_processing.assert_awaited_once_with(document_id)
    # The terminal DONE write still wins at the end of the run.
    database.jobs.mark_done.assert_awaited_once()


async def test_run_budget_falls_back_to_the_global_default_when_collection_is_null(
    jobs_core, monkeypatch
) -> None:
    """collection.job_timeout_seconds is NULL → the run is bounded by the worker's global default
    (context.job_timeout_seconds = 30.0 in the fake)."""
    database = _fake_database()
    document_id, context = _wire(
        jobs_core, monkeypatch, database, points=[MagicMock()], job_timeout_seconds=None
    )

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    assert context.runner.run.await_args.kwargs["timeout_seconds"] == 30.0


async def test_run_budget_uses_the_collection_override_when_set(jobs_core, monkeypatch) -> None:
    """A per-collection override caps the run's wall-clock, taking precedence over the global."""
    database = _fake_database()
    document_id, context = _wire(
        jobs_core, monkeypatch, database, points=[MagicMock()], job_timeout_seconds=99.0
    )

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    assert context.runner.run.await_args.kwargs["timeout_seconds"] == 99.0


async def test_run_budget_above_the_hard_ceiling_fails_fast_before_any_spend(
    jobs_core, monkeypatch
) -> None:
    """A per-collection budget above WORKER_JOB_TIMEOUT_MAX_SECONDS is a config error surfaced by
    name — the job fails BEFORE the pipeline runs (never silently truncated by arq's outer cap).
    It re-raises through the generic handler (arq accounts the attempt) after marking both truths."""
    import pytest  # noqa: PLC0415

    database = _fake_database()
    document_id, context = _wire(
        jobs_core, monkeypatch, database, points=[MagicMock()], job_timeout_seconds=99999.0
    )

    with pytest.raises(ValueError, match="WORKER_JOB_TIMEOUT_MAX_SECONDS"):
        await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    context.runner.run.assert_not_awaited()
    database.jobs.mark_done.assert_not_awaited()
    database.jobs.mark_failed.assert_awaited_once()
    database.ingestion.mark_failed.assert_awaited_once_with(document_id)
    error = database.jobs.mark_failed.await_args.kwargs["error"]
    assert "WORKER_JOB_TIMEOUT_MAX_SECONDS" in error


def test_resolve_run_budget_prefers_collection_then_default_then_rejects_over_ceiling(
    jobs_core,
) -> None:
    """The pure budget resolver: collection override wins, else the default; above the hard
    ceiling it raises a named ValueError (never returns a truncated value)."""
    import pytest  # noqa: PLC0415

    resolve = jobs_core._resolve_run_budget
    assert resolve(99.0, 30.0, 7200.0) == 99.0
    assert resolve(None, 30.0, 7200.0) == 30.0
    assert resolve(7200.0, 30.0, 7200.0) == 7200.0  # exactly the ceiling is allowed
    with pytest.raises(ValueError, match="WORKER_JOB_TIMEOUT_MAX_SECONDS"):
        resolve(7200.1, 30.0, 7200.0)


async def test_dequeue_skip_guard_bails_on_a_cancelled_job(jobs_core, monkeypatch) -> None:
    """A job cancelled while queued is already CANCELLED in the DB: the worker bails at dequeue —
    it never claims the job (mark_running) nor runs the pipeline, so the terminal state stands."""
    from shared_libs.services.db.postgresql.tables import JobStatus  # noqa: PLC0415

    database = _fake_database()
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])
    database.jobs.get = AsyncMock(return_value=SimpleNamespace(status=JobStatus.CANCELLED))

    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.jobs.mark_running.assert_not_awaited()
    database.ingestion.mark_processing.assert_not_awaited()
    context.runner.run.assert_not_awaited()
    database.jobs.mark_done.assert_not_awaited()


async def test_cooperative_cancel_at_boundary_terminates_without_failing(
    jobs_core, monkeypatch
) -> None:
    """A cancellation requested mid-run is honoured at the next stage boundary: the guard raises
    JobCancelledError, and the task marks the job CANCELLED (force_terminate) WITHOUT failing it,
    completing normally (no re-raise → arq does not retry)."""
    import sys  # noqa: PLC0415

    from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase  # noqa: PLC0415

    database = _fake_database()
    database.jobs.is_cancel_requested = AsyncMock(return_value=True)
    document_id, context = _wire(jobs_core, monkeypatch, database, points=[MagicMock()])
    # The cancel guard resolves services through its OWN module-level CONTEXT (jobs.cancellation),
    # so patch it to the same fake the core module uses.
    monkeypatch.setattr(sys.modules["jobs.cancellation"], "CONTEXT", context)
    # Give the blob a single root node so the guard has a stage boundary to probe.
    monkeypatch.setattr(
        jobs_core.BlobNormalizer,
        "normalize",
        lambda blob: {"nodes": [{"id": "n1", "kind": "intake", "family": "intake"}]},
    )

    async def _run(*args, **kwargs):
        # The engine would fire the run's progress callback at each node boundary; simulate the
        # START of the root node — where the cancel guard re-reads the flag and aborts.
        await kwargs["progress_callback"](
            ProgressEvent(phase=ProgressPhase.START, node_id="n1", kind="intake")
        )
        return (MagicMock(), MagicMock())

    context.runner.run = AsyncMock(side_effect=_run)

    # Must NOT raise — a cooperative cancel is a clean completion, not an arq failure.
    await jobs_core.ingest_document({}, str(document_id), str(uuid.uuid4()))

    database.jobs.force_terminate.assert_awaited_once()
    database.jobs.mark_done.assert_not_awaited()
    database.jobs.mark_failed.assert_not_awaited()
