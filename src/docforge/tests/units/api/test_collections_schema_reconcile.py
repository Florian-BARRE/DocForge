"""Collections router: a schema-change PATCH must RECONCILE the vector store and enqueue the repair
backfills — not merely flip an informational needs_reindex flag.

A field toggled filterable/semantic after first ingest is the risk: without reconcile its Qdrant
payload index / named vector is never provisioned and a filter silently returns 0 hits. These pin
that PATCH .../collections/{id} with a `fields` diff calls collections.reconcile_store (add missing
indexes live) AND queue.enqueue_backfill (repopulate existing points), while a PATCH that touches no
fields does neither. CONTEXT.database + CONTEXT.queue are mocked, so no store is touched.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.services.db.facades import CollectionUpdateResult

FAKE_ID = "22222222-2222-2222-2222-222222222222"


def _fake_collection() -> SimpleNamespace:
    return SimpleNamespace(
        id=FAKE_ID,
        name="c1",
        supported_formats=["pdf"],
        max_file_size_bytes=1_000_000,
        job_timeout_seconds=None,
        needs_reindex=False,
        created_at=None,
        pipeline={},
        search={},
    )


def _mock_ctx(monkeypatch, *, reconcile_return=None, **collections_methods):
    """Wire CONTEXT.database.collections + CONTEXT.queue with the given async mocks."""
    from backend.context import CONTEXT  # noqa: PLC0415

    facade = SimpleNamespace(
        reconcile_store=AsyncMock(return_value=reconcile_return or set()),
        **collections_methods,
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(collections=facade))
    queue = SimpleNamespace(enqueue_backfill=AsyncMock())
    monkeypatch.setattr(CONTEXT, "queue", queue)
    return facade, queue


def test_schema_change_patch_reconciles_and_enqueues_backfill(client, monkeypatch) -> None:
    fake = _fake_collection()
    facade, queue = _mock_ctx(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_schema=AsyncMock(return_value=[]),
        apply_update=AsyncMock(
            return_value=CollectionUpdateResult(schema_applied=True, schema_reindex_required=True)
        ),
    )

    response = client.patch(
        f"/api/v1/collections/{FAKE_ID}",
        json={"fields": [{"field_name": "author", "field_type": "string", "filterable": True}]},
    )
    assert response.status_code == 200, response.text

    # The atomic PATCH ran, then (AFTER the DB commit) the store was reconciled (missing indexes added
    # live) AND the repair backfills were enqueued.
    facade.apply_update.assert_awaited_once()
    facade.reconcile_store.assert_awaited_once_with(uuid.UUID(FAKE_ID))
    queue.enqueue_backfill.assert_awaited_once_with(FAKE_ID)


def test_reconcile_still_runs_when_surface_unchanged(client, monkeypatch) -> None:
    """A fields diff that does not move the searchable surface (schema_reindex_required=False) still
    reconciles + backfills: a metadata-only edit is cheap and idempotent to repair."""
    fake = _fake_collection()
    facade, queue = _mock_ctx(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_schema=AsyncMock(return_value=[]),
        apply_update=AsyncMock(
            return_value=CollectionUpdateResult(schema_applied=True, schema_reindex_required=False)
        ),
    )

    response = client.patch(
        f"/api/v1/collections/{FAKE_ID}",
        json={"fields": [{"field_name": "author", "field_type": "string"}]},
    )
    assert response.status_code == 200, response.text
    facade.reconcile_store.assert_awaited_once()
    queue.enqueue_backfill.assert_awaited_once()


def test_non_schema_patch_does_not_reconcile_or_backfill(client, monkeypatch) -> None:
    """A rename-only PATCH touches no schema — no store reconcile, no backfill enqueue."""
    fake = _fake_collection()
    facade, queue = _mock_ctx(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[]),
        apply_update=AsyncMock(
            return_value=CollectionUpdateResult(schema_applied=False, schema_reindex_required=False)
        ),
    )

    response = client.patch(f"/api/v1/collections/{FAKE_ID}", json={"name": "renamed"})
    assert response.status_code == 200, response.text
    facade.reconcile_store.assert_not_awaited()
    queue.enqueue_backfill.assert_not_awaited()
