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

    auth = SimpleNamespace(grant_collection_to_key=AsyncMock(return_value=True))
    context = SimpleNamespace(
        database=SimpleNamespace(transfer=object(), transfer_tracker=tracker, auth=auth),
        s3=SimpleNamespace(bucket="bucket", client=_client),
        RUNTIME_CONFIG=SimpleNamespace(
            DOCFORGE_VERSION="test",
            EXPORT_COMPRESSION="none",
            EXPORT_BUNDLE_PREFIX="col-exports",
            EXPORT_TTL_SECONDS=3600,
            IMPORT_MAX_DECOMPRESSION_RATIO=100,
            IMPORT_MAX_MEMBERS=500_000,
        ),
        logger=SimpleNamespace(
            debug=lambda *a, **k: None,
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            exception=lambda *a, **k: None,
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

    # download_to writes the bundle to the target path; the import task now stats it to derive the
    # decompression-bomb ceiling, so the mock must actually create the file.
    async def _fake_download(_client, _bucket, _key, archive_path):
        archive_path.write_bytes(b"bundle-bytes")

    monkeypatch.setattr(
        jobs_transfer.S3ObjectApi, "download_to", AsyncMock(side_effect=_fake_download)
    )
    delete_staged = AsyncMock()
    monkeypatch.setattr(jobs_transfer.S3ObjectApi, "delete", delete_staged)
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
    # The staged bundle is reclaimed on success so it does not leak in S3 (GC sweeps exports only).
    delete_staged.assert_awaited_once()
    assert delete_staged.await_args.args[2] == "col-exports/x.dcexport"
    # The new collection's NAME (not just its id) is stamped on the tracking row, so a polled
    # transfer surfaces the real name instead of a null the UI falls back to generic text for.
    done_kwargs = tracker.mark_done.await_args.kwargs
    assert done_kwargs["collection_id"] == new_id
    assert done_kwargs["collection_name"] == "DemoCollection (imported)"
    tracker.mark_failed.assert_not_awaited()


def _patch_import_engine(jobs_transfer, monkeypatch, new_id):
    """Stub the download/unpack/reader/importer chain so import_collection reaches its grant step."""
    monkeypatch.setattr(
        jobs_transfer,
        "BundleReader",
        lambda _root: SimpleNamespace(validate=lambda: SimpleNamespace(format_version=1)),
    )

    async def _fake_download(_client, _bucket, _key, archive_path):
        archive_path.write_bytes(b"bundle-bytes")

    monkeypatch.setattr(
        jobs_transfer.S3ObjectApi, "download_to", AsyncMock(side_effect=_fake_download)
    )
    monkeypatch.setattr(jobs_transfer.S3ObjectApi, "delete", AsyncMock())
    monkeypatch.setattr(jobs_transfer.BundleArchive, "unpack", staticmethod(lambda *a, **k: None))
    import_result = SimpleNamespace(
        collection_id=new_id, collection_name="Imported", counts={"documents": 1}
    )
    monkeypatch.setattr(
        jobs_transfer,
        "get_importer",
        lambda *a, **k: SimpleNamespace(run=AsyncMock(return_value=import_result)),
    )


async def test_import_grants_ownership_when_key_provided(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    new_id = uuid.uuid4()
    _patch_import_engine(jobs_transfer, monkeypatch, new_id)
    key_id = str(uuid.uuid4())

    await jobs_transfer.import_collection(
        {}, "col-exports/x.dcexport", str(uuid.uuid4()), None, key_id
    )

    # The creating key is granted ownership of the imported collection (id as string).
    context.database.auth.grant_collection_to_key.assert_awaited_once_with(
        uuid.UUID(key_id), str(new_id)
    )
    tracker.mark_done.assert_awaited_once()
    tracker.mark_failed.assert_not_awaited()


async def test_import_grant_failure_does_not_fail_a_done_import(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    new_id = uuid.uuid4()
    _patch_import_engine(jobs_transfer, monkeypatch, new_id)
    # The ownership grant blows up — a best-effort step that must NOT fail a DONE import.
    context.database.auth.grant_collection_to_key = AsyncMock(side_effect=RuntimeError("boom"))

    result = await jobs_transfer.import_collection(
        {}, "col-exports/x.dcexport", str(uuid.uuid4()), None, str(uuid.uuid4())
    )

    # The import still succeeded: the row is DONE, never FAILED, and the result surfaces the id.
    assert result["collection_id"] == str(new_id)
    tracker.mark_done.assert_awaited_once()
    tracker.mark_failed.assert_not_awaited()


async def test_import_without_key_skips_grant(jobs_transfer, monkeypatch):
    context, tracker = _context(monkeypatch, jobs_transfer)
    _patch_import_engine(jobs_transfer, monkeypatch, uuid.uuid4())

    await jobs_transfer.import_collection(
        {}, "col-exports/x.dcexport", str(uuid.uuid4()), None, None
    )

    # A full-access / keyless caller threads no key id → no grant attempted.
    context.database.auth.grant_collection_to_key.assert_not_awaited()
