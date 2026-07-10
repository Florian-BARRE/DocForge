"""Documents router: fail-fast on a STALE stored pipeline blob at upload time.

A collection whose stored ``pipeline`` blob no longer builds — here a metagen node with the
removed ``kind="chunk"`` (the real DemoCollection incident) — must be rejected with a 422 BEFORE
any spend: no dedup lookup, no bytes stored, no document/job admitted, no job enqueued. This
guards DocForge invariant #4 (structural fail-fast before spend) on the upload path, which
previously had no pipeline validation at all.

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
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(collections=collections, ingestion=ingestion))
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

    # 1. A stale blob is DATA → 422 (never a 500, never the 202 accept path).
    assert response.status_code == 422, response.text

    # 2. The message names the offending node/kind so the caller knows exactly what is stale.
    assert "meta_chunk" in response.text
    assert "chunk" in response.text

    # 3. NOTHING was spent: no dedup lookup, no store, no admit, no enqueue.
    spies.ingestion.find_duplicate.assert_not_called()
    spies.ingestion.store_blobs.assert_not_called()
    spies.ingestion.admit.assert_not_called()
    spies.queue.enqueue_ingest.assert_not_called()
