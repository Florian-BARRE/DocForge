"""Documents router: an UN-MIGRATABLE stored pipeline blob fails fast + clear at upload time.

A stored blob is auto-healed to the current engine (BlobNormalizer round-trip) — a merely
stale-but-readable blob is normalized, never rejected. But a blob that references something the
current engine no longer knows — here a metagen node with the removed ``kind="chunk"`` (the real
DemoCollection incident) — cannot be migrated: it is rejected with a 422 BEFORE any spend (no
dedup lookup, no bytes stored, no document/job admitted, no job enqueued), carrying a clear,
actionable message (the cause + the one recovery: re-save from the default). This guards DocForge
invariant #4 (structural fail-fast before spend) and eliminates the cryptic foreach_invalid_body.

CONTEXT is patched with recording fakes so the endpoint runs without a store — the point is
exactly that the downstream (store/admit/enqueue) is never reached. ``from backend...`` imports
are deferred to inside the test, after the ``fastapi_app`` fixture has registered app/ on sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# A metagen node with kind "chunk" — a kind the P5 restructure removed from the registry, so the
# builder raises BuildError("... No node registered for family 'metagen', kind 'chunk' ...").
STALE_PIPELINE_BLOB = {
    "id": "root",
    "nodes": [{"id": "meta_chunk", "family": "metagen", "kind": "chunk", "config": {}}],
    "transitions": [],
    "bindings": {},
}


def _install_recording_context(monkeypatch, fastapi_app) -> SimpleNamespace:
    """Patch CONTEXT with a collection returning the stale blob + recording spend fakes."""
    # 1. Deferred import — app/ is on sys.path only after fastapi_app booted.
    from backend.context import CONTEXT  # noqa: PLC0415

    # 2. The collection exists and carries the stale blob (step 1 of the handler succeeds).
    collection = SimpleNamespace(pipeline=STALE_PIPELINE_BLOB)
    collections = SimpleNamespace(
        get=AsyncMock(return_value=collection),
        get_schema=AsyncMock(return_value=[]),
    )

    # 3. Every downstream "spend" is a spy that must stay untouched.
    ingestion = SimpleNamespace(
        find_duplicate=AsyncMock(return_value=None),
        store_blobs=AsyncMock(),
        admit=AsyncMock(return_value=(None, None)),
    )
    queue = SimpleNamespace(enqueue_ingest=AsyncMock())

    # 4. Swap them onto CONTEXT (monkeypatch reverts after the test).
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, ingestion=ingestion)
    )
    monkeypatch.setattr(CONTEXT, "queue", queue)

    return SimpleNamespace(collections=collections, ingestion=ingestion, queue=queue)


def test_upload_with_stale_pipeline_blob_is_422_and_spends_nothing(
    client, fastapi_app, monkeypatch
) -> None:
    spies = _install_recording_context(monkeypatch, fastapi_app)

    response = client.post(
        "/api/v1/documents",
        data={"collection_id": str(uuid.uuid4()), "metadata": "{}"},
        files={"file": ("doc.txt", b"hello world", "text/plain")},
    )

    # 1. An un-migratable blob is DATA → 422 (never a 500, never the 202 accept path).
    assert response.status_code == 422, response.text

    # 2. The message is clear + actionable: it names the recovery (re-save from default) and
    #    surfaces the underlying cause, so the caller knows what is wrong and how to fix it.
    assert "re-save" in response.text
    assert "chunk" in response.text

    # 3. NOTHING was spent: no dedup lookup, no store, no admit, no enqueue.
    spies.ingestion.find_duplicate.assert_not_called()
    spies.ingestion.store_blobs.assert_not_called()
    spies.ingestion.admit.assert_not_called()
    spies.queue.enqueue_ingest.assert_not_called()


def test_upload_with_out_of_enum_metadata_value_is_422_at_the_boundary(
    client, fastapi_app, monkeypatch
) -> None:
    """An out-of-enum declared value fails fast (422) at upload — enum membership is structural, so
    the caller does not have to poll a job to discover it. Nothing is stored/admitted/enqueued."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from shared_libs.pipelines.ingest import IngestPipeline  # noqa: PLC0415

    collection = SimpleNamespace(
        pipeline=IngestPipeline.default_blob().model_dump(mode="json"),
        max_file_size_bytes=5_000_000,
        job_timeout_seconds=None,
        supported_formats=["pdf"],
    )
    jurisdiction = SimpleNamespace(id=1, field_name="jurisdiction", enum_values=["EU", "US"])
    collections = SimpleNamespace(
        get=AsyncMock(return_value=collection),
        get_schema=AsyncMock(return_value=[jurisdiction]),
    )
    ingestion = SimpleNamespace(
        find_duplicate=AsyncMock(return_value=None),
        store_blobs=AsyncMock(),
        admit=AsyncMock(return_value=(None, None)),
    )
    queue = SimpleNamespace(enqueue_ingest=AsyncMock())
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, ingestion=ingestion)
    )
    monkeypatch.setattr(CONTEXT, "queue", queue)

    response = client.post(
        "/api/v1/documents",
        data={"collection_id": str(uuid.uuid4()), "metadata": '{"jurisdiction": "MARS"}'},
        files={"file": ("doc.pdf", b"%PDF-1.4 hello", "application/pdf")},
    )

    assert response.status_code == 422, response.text
    assert "not one of" in response.text and "MARS" in response.text
    ingestion.store_blobs.assert_not_called()
    ingestion.admit.assert_not_called()
    queue.enqueue_ingest.assert_not_called()


def _install_format_context(monkeypatch, fastapi_app, supported_formats: list[str]):
    """Patch CONTEXT with a healthy collection accepting ``supported_formats`` + spend spies."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from shared_libs.pipelines.ingest import IngestPipeline  # noqa: PLC0415

    collection = SimpleNamespace(
        pipeline=IngestPipeline.default_blob().model_dump(mode="json"),
        max_file_size_bytes=5_000_000,
        job_timeout_seconds=None,
        supported_formats=supported_formats,
    )
    collections = SimpleNamespace(
        get=AsyncMock(return_value=collection),
        get_schema=AsyncMock(return_value=[]),
    )
    ingestion = SimpleNamespace(
        find_duplicate=AsyncMock(return_value=None),
        store_blobs=AsyncMock(),
        admit=AsyncMock(
            return_value=(SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4()))
        ),
    )
    queue = SimpleNamespace(enqueue_ingest=AsyncMock())
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, ingestion=ingestion)
    )
    monkeypatch.setattr(CONTEXT, "queue", queue)
    return SimpleNamespace(ingestion=ingestion, queue=queue)


def test_upload_with_unsupported_format_is_422_and_spends_nothing(
    client, fastapi_app, monkeypatch
) -> None:
    """A format outside the collection's supported_formats is rejected FAST (422) at the upload
    endpoint — on the DETECTED format (a zip-container xlsx here), before any blob is stored or job
    enqueued — instead of failing minutes later inside the queued run's admit node."""
    import io  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    spies = _install_format_context(monkeypatch, fastapi_app, supported_formats=["pdf", "txt"])

    # Build a minimal real xlsx (OOXML zip with an xl/ member) so the content probe detects 'xlsx'.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
    xlsx_bytes = buffer.getvalue()

    response = client.post(
        "/api/v1/documents",
        data={"collection_id": str(uuid.uuid4()), "metadata": "{}"},
        files={
            "file": (
                "sheet.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    # 1. Rejected at the boundary, on the detected format, with an actionable allow-list message.
    assert response.status_code == 422, response.text
    assert "xlsx" in response.text and "not accepted" in response.text
    assert "pdf" in response.text  # the allowed set is surfaced

    # 2. Nothing was spent: no blob stored, no admit, no enqueue.
    spies.ingestion.store_blobs.assert_not_called()
    spies.ingestion.admit.assert_not_called()
    spies.queue.enqueue_ingest.assert_not_called()


def test_upload_with_supported_format_still_accepts_202(client, fastapi_app, monkeypatch) -> None:
    """A supported (detected) format sails through the new gate — still a 202 accept + enqueue."""
    spies = _install_format_context(monkeypatch, fastapi_app, supported_formats=["pdf"])

    response = client.post(
        "/api/v1/documents",
        data={"collection_id": str(uuid.uuid4()), "metadata": "{}"},
        files={"file": ("doc.pdf", b"%PDF-1.4 hello world", "application/pdf")},
    )

    assert response.status_code == 202, response.text
    spies.ingestion.store_blobs.assert_called_once()
    spies.queue.enqueue_ingest.assert_called_once()
