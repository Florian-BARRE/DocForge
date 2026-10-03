"""sync_document_metadata — the per-document metadata re-embed arq task drives its PRE-CREATED tracked
job row through the lifecycle so the UI can watch it complete: RUNNING at start, DONE on success,
FAILED (and re-raised) on error. The sync facades themselves are covered elsewhere; here we assert the
job-lifecycle contract only (serviceless — every facade is mocked)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _fake_context(*, meta_points=5, filter_points=5, meta_error: Exception | None = None):
    """A worker CONTEXT whose jobs/meta_vectors/filters facades are AsyncMocks."""
    meta_sync = (
        AsyncMock(side_effect=meta_error)
        if meta_error is not None
        else AsyncMock(return_value=meta_points)
    )
    return SimpleNamespace(
        worker_id="worker-1",
        logger=SimpleNamespace(info=lambda *a, **k: None),
        database=SimpleNamespace(
            jobs=SimpleNamespace(
                mark_running=AsyncMock(),
                mark_done=AsyncMock(),
                mark_failed=AsyncMock(),
            ),
            meta_vectors=SimpleNamespace(sync_document_meta_vectors=meta_sync),
            filters=SimpleNamespace(
                sync_document_filter_payloads=AsyncMock(return_value=filter_points)
            ),
        ),
    )


async def test_success_runs_then_completes_the_tracked_job(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context(meta_points=4, filter_points=6)
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)
    document_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())

    result = await jobs_metadata_sync.sync_document_metadata({"job_try": 1}, document_id, job_id)

    assert result == {"meta_points": 4, "filter_points": 6}
    # RUNNING claimed before the work, DONE after it, never FAILED.
    context.database.jobs.mark_running.assert_awaited_once()
    context.database.jobs.mark_done.assert_awaited_once()
    context.database.jobs.mark_failed.assert_not_awaited()
    # The job id is coerced to a UUID for every lifecycle call.
    assert context.database.jobs.mark_running.await_args.args[0] == uuid.UUID(job_id)


async def test_failure_fails_the_tracked_job_and_reraises(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context(meta_error=RuntimeError("qdrant down"))
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)
    document_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())

    with pytest.raises(RuntimeError, match="qdrant down"):
        await jobs_metadata_sync.sync_document_metadata({}, document_id, job_id)

    # Marked FAILED with the error type, never DONE; the raise lets arq account the attempt.
    context.database.jobs.mark_failed.assert_awaited_once()
    assert context.database.jobs.mark_failed.await_args.kwargs["error_type"] == "RuntimeError"
    context.database.jobs.mark_done.assert_not_awaited()


async def test_running_claim_carries_worker_id_and_attempt(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context()
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)

    await jobs_metadata_sync.sync_document_metadata(
        {"job_try": 3}, str(uuid.uuid4()), str(uuid.uuid4())
    )

    kwargs = context.database.jobs.mark_running.await_args.kwargs
    assert kwargs["worker_id"] == "worker-1"
    assert kwargs["attempt"] == 3
    assert context.database.jobs.mark_done.await_args.kwargs["finished_at"] is not None


async def test_attempt_defaults_to_one_without_job_try(jobs_metadata_sync, monkeypatch) -> None:
    context = _fake_context()
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)

    await jobs_metadata_sync.sync_document_metadata({}, str(uuid.uuid4()), str(uuid.uuid4()))

    assert context.database.jobs.mark_running.await_args.kwargs["attempt"] == 1


async def test_filter_repaint_failure_fails_the_job_with_the_error_text(
    jobs_metadata_sync, monkeypatch
) -> None:
    """The second sync step failing (after meta vectors succeeded) is also a FAILED job, re-raised."""
    context = _fake_context()
    context.database.filters.sync_document_filter_payloads = AsyncMock(
        side_effect=ValueError("bad payload")
    )
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)
    job_id = str(uuid.uuid4())

    with pytest.raises(ValueError, match="bad payload"):
        await jobs_metadata_sync.sync_document_metadata({}, str(uuid.uuid4()), job_id)

    failed = context.database.jobs.mark_failed.await_args
    assert failed.args[0] == uuid.UUID(job_id)
    assert failed.kwargs["error"] == "bad payload"
    assert failed.kwargs["error_type"] == "ValueError"
    context.database.jobs.mark_done.assert_not_awaited()


async def test_claim_failure_propagates_without_marking_failed(
    jobs_metadata_sync, monkeypatch
) -> None:
    """mark_running sits OUTSIDE the try: if the claim itself fails nothing ran, so nothing is failed."""
    context = _fake_context()
    context.database.jobs.mark_running = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)

    with pytest.raises(RuntimeError, match="db down"):
        await jobs_metadata_sync.sync_document_metadata({}, str(uuid.uuid4()), str(uuid.uuid4()))

    context.database.jobs.mark_failed.assert_not_awaited()
    context.database.meta_vectors.sync_document_meta_vectors.assert_not_awaited()


async def test_invalid_job_id_raises_before_any_lifecycle_call(
    jobs_metadata_sync, monkeypatch
) -> None:
    context = _fake_context()
    monkeypatch.setattr(jobs_metadata_sync, "CONTEXT", context)

    with pytest.raises(ValueError):
        await jobs_metadata_sync.sync_document_metadata({}, str(uuid.uuid4()), "not-a-uuid")

    context.database.jobs.mark_running.assert_not_awaited()
