"""Corpus bulk ops over the shared DocumentSelector: delete / set-enabled / reingest. Covers the
selector XOR contract (422, serviceless — Pydantic rejects before the handler), the validate-before-
spend fail-fast ordering (404 collection, 403 scope, 422 bad selector / stale pipeline BEFORE any
mutation or enqueue), selector resolution (explicit ids vs filter+exclude), the fan-out cap, and the
empty/no-match edges. No live stack — the façades + queue are mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.services.db.facades import ReingestOutcome, ReingestResult

COLLECTION_ID = uuid.uuid4()


def _admitted(document, job) -> ReingestResult:
    """A reingest admission that minted a fresh job (the happy path)."""
    return ReingestResult(outcome=ReingestOutcome.ADMITTED, document=document, job=job)


# -------------------- selector shape (serviceless 422) --------------------
def test_selector_rejects_both_modes(client) -> None:
    """Both document_ids AND filter set → Pydantic 422 before the handler (no store touched)."""
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"document_ids": [str(uuid.uuid4())], "filter": {}},
    )
    assert response.status_code == 422


def test_selector_rejects_neither_mode(client) -> None:
    """Neither document_ids nor filter → 422 (exactly one mode is required)."""
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/documents/delete", json={})
    assert response.status_code == 422


def test_selector_rejects_empty_ids(client) -> None:
    """An empty explicit id list is an ambiguous no-op → 422."""
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete", json={"document_ids": []}
    )
    assert response.status_code == 422


def test_selector_rejects_exclude_in_id_mode(client) -> None:
    """exclude_ids only makes sense in filter mode → 422 when paired with document_ids."""
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"document_ids": [str(uuid.uuid4())], "exclude_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 422


# -------------------- bulk delete --------------------
def test_bulk_delete_unknown_collection_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    collections = SimpleNamespace(get=AsyncMock(return_value=None))
    delete_many = AsyncMock()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=collections, documents=SimpleNamespace(delete_many=delete_many)
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"document_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 404
    delete_many.assert_not_awaited()  # never mutated on an unknown collection


def test_bulk_delete_foreign_id_is_422_before_delete(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    foreign = SimpleNamespace(id=uuid.uuid4(), collection_id=uuid.uuid4())
    delete_many = AsyncMock()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                get_by_ids=AsyncMock(return_value=[foreign]), delete_many=delete_many
            ),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"document_ids": [str(foreign.id)]},
    )
    assert response.status_code == 422
    assert "not in collection" in response.json()["detail"]
    delete_many.assert_not_awaited()


def test_bulk_delete_explicit_ids(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    doc = SimpleNamespace(id=uuid.uuid4(), collection_id=COLLECTION_ID)
    delete_many = AsyncMock(return_value=1)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                get_by_ids=AsyncMock(return_value=[doc]), delete_many=delete_many
            ),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"document_ids": [str(doc.id)]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] == 1 and body["deleted"] == 1
    delete_many.assert_awaited_once_with([doc.id])


def test_bulk_delete_filter_minus_exclude(client, monkeypatch) -> None:
    """Filter mode resolves every matching id, then removes the deselected ones (select-all-minus-N)."""
    from backend.context import CONTEXT

    keep, drop = uuid.uuid4(), uuid.uuid4()
    delete_many = AsyncMock(return_value=1)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                resolve_query_ids=AsyncMock(return_value=[keep, drop]), delete_many=delete_many
            ),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete",
        json={"filter": {}, "exclude_ids": [str(drop)]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["matched"] == 1
    delete_many.assert_awaited_once_with([keep])


def test_bulk_delete_filter_no_match_is_zero(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    delete_many = AsyncMock(return_value=0)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                resolve_query_ids=AsyncMock(return_value=[]), delete_many=delete_many
            ),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete", json={"filter": {}}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] == 0 and body["deleted"] == 0 and body["capped"] is False
    delete_many.assert_awaited_once_with([])


def test_bulk_delete_caps_selection_and_signals(client, monkeypatch) -> None:
    """A filter matching MORE than the selection cap deletes only the first N and reports capped=true.

    The resolution is bounded (never a 100k-id set in memory) and the truncation is SIGNALLED, not
    silent — delete is convergent, so the caller re-runs the same selector for the remainder.
    """
    from backend.context import CONTEXT
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "CORPUS_MAX_DELETE_SELECTION", 2)
    # The bounded probe fetches cap + 1 ids; the DB honours the limit, so it returns 3 (2 kept + 1
    # signalling more remain). The mock returns exactly what the limited query would.
    matched = [uuid.uuid4() for _ in range(3)]
    delete_many = AsyncMock(return_value=2)
    resolve_query_ids = AsyncMock(return_value=matched)
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(resolve_query_ids=resolve_query_ids, delete_many=delete_many),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/delete", json={"filter": {}}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capped"] is True and body["max_selection"] == 2
    assert body["matched"] == 2 and body["deleted"] == 2
    # Only the first N (the cap) are deleted; the probe id is dropped.
    delete_many.assert_awaited_once_with(matched[:2])
    # The read was bounded to cap + 1 (the probe), never an unbounded resolution.
    assert resolve_query_ids.await_args.args[-1] == 3


# -------------------- bulk set-enabled --------------------
def test_bulk_set_enabled_reports_matched_vs_updated(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    ids = [uuid.uuid4(), uuid.uuid4()]
    docs = [SimpleNamespace(id=i, collection_id=COLLECTION_ID) for i in ids]
    set_documents_enabled = AsyncMock(return_value=1)  # one already in-state
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(get_by_ids=AsyncMock(return_value=docs)),
            enablement=SimpleNamespace(set_documents_enabled=set_documents_enabled),
        ),
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/set-enabled?enabled=false",
        json={"document_ids": [str(i) for i in ids]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is False
    assert body["matched"] == 2 and body["updated"] == 1
    assert body["reindex_implied"] is False
    set_documents_enabled.assert_awaited_once_with(ids, False)


# -------------------- bulk reingest --------------------
def _patch_pipeline_validation(monkeypatch) -> None:
    """Make the fail-fast blob heal + structural validate no-ops (tested elsewhere)."""
    import importlib

    router_module = importlib.import_module("backend.routers.corpus.router")
    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(lambda blob: {}))
    monkeypatch.setattr(
        router_module.PipelineBlobValidator, "validate", classmethod(lambda cls, blob: None)
    )


def test_bulk_reingest_broken_pipeline_422_before_spend(client, monkeypatch) -> None:
    import importlib

    from backend.context import CONTEXT

    router_module = importlib.import_module("backend.routers.corpus.router")

    def _raise(blob):
        raise router_module.BlobNormalizationError("broken node config")

    monkeypatch.setattr(router_module.BlobNormalizer, "normalize", staticmethod(_raise))
    enqueue = AsyncMock()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID, pipeline={})),
            ),
        ),
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/reingest", json={"filter": {}}
    )
    assert response.status_code == 422
    enqueue.assert_not_awaited()


def test_bulk_reingest_filter_fans_out(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    _patch_pipeline_validation(monkeypatch)
    ids = [uuid.uuid4() for _ in range(3)]
    docs = [SimpleNamespace(id=i, collection_id=COLLECTION_ID) for i in ids]
    jobs = [SimpleNamespace(id=uuid.uuid4()) for _ in ids]
    enqueue = AsyncMock()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(
                    return_value=SimpleNamespace(
                        id=COLLECTION_ID, pipeline={}, job_timeout_seconds=None
                    )
                ),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                resolve_query_ids=AsyncMock(return_value=ids),
                get_by_ids=AsyncMock(return_value=docs),
            ),
            ingestion=SimpleNamespace(
                reingest=AsyncMock(side_effect=[_admitted(docs[i], jobs[i]) for i in range(3)])
            ),
            # The shared enqueue helper reads database.jobs (only touched on a queue failure).
            jobs=SimpleNamespace(mark_failed=AsyncMock()),
        ),
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/reingest", json={"filter": {}}
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["matched"] == 3 and body["enqueued"] == 3 and body["capped"] is False
    assert enqueue.await_count == 3


def test_bulk_reingest_caps_fanout(client, monkeypatch) -> None:
    from backend.context import CONTEXT
    from config import RUNTIME_CONFIG

    _patch_pipeline_validation(monkeypatch)
    monkeypatch.setattr(RUNTIME_CONFIG, "CORPUS_MAX_REINGEST_FANOUT", 2)
    matched = [uuid.uuid4() for _ in range(5)]
    docs = [SimpleNamespace(id=i, collection_id=COLLECTION_ID) for i in matched[:2]]
    jobs = [SimpleNamespace(id=uuid.uuid4()) for _ in docs]
    enqueue = AsyncMock()
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(
            collections=SimpleNamespace(
                get=AsyncMock(
                    return_value=SimpleNamespace(
                        id=COLLECTION_ID, pipeline={}, job_timeout_seconds=None
                    )
                ),
                get_schema=AsyncMock(return_value=[]),
            ),
            documents=SimpleNamespace(
                resolve_query_ids=AsyncMock(return_value=matched),
                get_by_ids=AsyncMock(return_value=docs),
            ),
            ingestion=SimpleNamespace(
                reingest=AsyncMock(
                    side_effect=[_admitted(docs[0], jobs[0]), _admitted(docs[1], jobs[1])]
                )
            ),
            # The shared enqueue helper reads database.jobs (only touched on a queue failure).
            jobs=SimpleNamespace(mark_failed=AsyncMock()),
        ),
    )
    monkeypatch.setattr(CONTEXT.queue, "enqueue_ingest", enqueue)
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/reingest", json={"filter": {}}
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["matched"] == 5 and body["enqueued"] == 2
    assert body["capped"] is True and body["max_fanout"] == 2
