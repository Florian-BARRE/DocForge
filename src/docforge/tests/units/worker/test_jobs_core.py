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
            mark_running=AsyncMock(), mark_done=AsyncMock(), mark_failed=AsyncMock()
        ),
        documents=SimpleNamespace(get=AsyncMock(), get_metadata=AsyncMock(return_value=[])),
        collections=SimpleNamespace(get=AsyncMock(), get_schema=AsyncMock(return_value=[])),
        ingestion=SimpleNamespace(
            store_blobs=AsyncMock(), save=AsyncMock(), index=AsyncMock(), mark_failed=AsyncMock()
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
        RUNTIME_CONFIG=SimpleNamespace(WORKER_PREFLIGHT_ENABLED=True),
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
