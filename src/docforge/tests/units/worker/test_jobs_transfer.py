"""export_collection / import_collection arq tasks: the contract around the engine — string ids
coerced, the tracking row driven RUNNING → DONE (FAILED on error), the artifact reference stamped
for export, and the new collection id surfaced for import. The heavy engine is stubbed (it has its
own tests); this pins the task's orchestration + return shape."""

import contextlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _context(monkeypatch, jobs_transfer):
    """A fake worker CONTEXT with an AsyncMock tracker, a dummy s3 client scope and config."""
    tracker = SimpleNamespace(
        mark_running=AsyncMock(),
        report_progress=AsyncMock(),
        set_artifact=AsyncMock(),
        mark_done=AsyncMock(),
        mark_failed=AsyncMock(),
    )

    @contextlib.asynccontextmanager
    async def _client():
        yield object()

    context = SimpleNamespace(
        database=SimpleNamespace(transfer=object(), transfer_tracker=tracker),
        s3=SimpleNamespace(bucket="bucket", client=_client),
        RUNTIME_CONFIG=SimpleNamespace(
            DOCFORGE_VERSION="test",
            EXPORT_COMPRESSION="none",
            EXPORT_BUNDLE_PREFIX="col-exports",
            EXPORT_TTL_SECONDS=3600,
        ),
        logger=SimpleNamespace(
            debug=lambda *a, **k: None, info=lambda *a, **k: None, exception=lambda *a, **k: None
        ),
    )
    monkeypatch.setattr(jobs_transfer, "CONTEXT", context)
    return context, tracker


async def test_export_collection_returns_reference_and_marks_done(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    manifest = SimpleNamespace(
        format_version=1,
        dense_dim=1024,
        counts=SimpleNamespace(model_dump=lambda: {"documents": 2, "points": 5}),
    )
    fake_exporter = SimpleNamespace(build=AsyncMock(return_value=manifest))
    monkeypatch.setattr(jobs_transfer, "CollectionExporter", lambda *a, **k: fake_exporter)
    monkeypatch.setattr(jobs_transfer.BundleArchive, "pack", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(jobs_transfer.S3ObjectApi, "put_file", AsyncMock(return_value=4242))
    collection_id, transfer_id = str(uuid.uuid4()), str(uuid.uuid4())

    result = await jobs_transfer.export_collection({}, collection_id, transfer_id)

    assert result["s3_key"] == f"col-exports/{transfer_id}.dcexport"
    assert result["size_bytes"] == 4242
    assert result["counts"] == {"documents": 2, "points": 5}
    tracker.mark_running.assert_awaited_once()
    tracker.set_artifact.assert_awaited_once()
    tracker.mark_done.assert_awaited_once()
    tracker.mark_failed.assert_not_awaited()


async def test_export_collection_marks_failed_and_reraises(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    failing = SimpleNamespace(build=AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(jobs_transfer, "CollectionExporter", lambda *a, **k: failing)

    with pytest.raises(RuntimeError):
        await jobs_transfer.export_collection({}, str(uuid.uuid4()), str(uuid.uuid4()))

    tracker.mark_failed.assert_awaited_once()
    tracker.mark_done.assert_not_awaited()


async def test_import_collection_returns_new_collection_and_marks_done(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    new_id = uuid.uuid4()
    manifest = SimpleNamespace(format_version=1)
    fake_reader = SimpleNamespace(validate=lambda: manifest)
    monkeypatch.setattr(jobs_transfer, "BundleReader", lambda _root: fake_reader)
    monkeypatch.setattr(jobs_transfer.S3ObjectApi, "download_to", AsyncMock(return_value=None))
    monkeypatch.setattr(jobs_transfer.BundleArchive, "unpack", staticmethod(lambda *a, **k: None))
    import_result = SimpleNamespace(
        collection_id=new_id, collection_name="DemoCollection (imported)", counts={"documents": 2}
    )
    fake_importer = SimpleNamespace(run=AsyncMock(return_value=import_result))
    monkeypatch.setattr(jobs_transfer, "get_importer", lambda *a, **k: fake_importer)

    result = await jobs_transfer.import_collection({}, "col-exports/x.dcexport", str(uuid.uuid4()))

    assert result["collection_id"] == str(new_id)
    assert result["collection_name"] == "DemoCollection (imported)"
    tracker.mark_done.assert_awaited_once()
    # The new collection's NAME (not just its id) is stamped on the tracking row, so a polled
    # transfer surfaces the real name instead of a null the UI falls back to generic text for.
    done_kwargs = tracker.mark_done.await_args.kwargs
    assert done_kwargs["collection_id"] == new_id
    assert done_kwargs["collection_name"] == "DemoCollection (imported)"
    tracker.mark_failed.assert_not_awaited()
