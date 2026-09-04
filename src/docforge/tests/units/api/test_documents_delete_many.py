"""DocumentsFacade.delete_many — the batched, set-based bulk delete (prod-safety #2). It must:
process the matched set in BOUNDED chunks (one short transaction each), stay set-based (no per-doc
round-trip), keep the single-delete's coherent order (Qdrant points via MatchAny per collection →
Postgres cascade → orphan-only S3 purge), de-duplicate ids, and never silently drop targets. All
three stores are mocked; the data-access APIs are patched on the facade module."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import DocumentsFacade
from shared_libs.services.db.facades import documents_facade as df_module


def _session_mock() -> MagicMock:
    """A session mock with an awaitable ``flush`` (the facade awaits it inside each batch)."""
    session = MagicMock()
    session.flush = AsyncMock()
    return session


def _postgres_yielding(session: MagicMock) -> MagicMock:
    """A postgres mock whose session() is an async context manager yielding ``session``."""

    @asynccontextmanager
    async def _session():
        yield session

    postgres = MagicMock()
    postgres.session = _session
    return postgres


def _s3_client() -> MagicMock:
    """An S3 mock whose client() is an async context manager yielding a raw client."""

    @asynccontextmanager
    async def _client():
        yield MagicMock()

    s3 = MagicMock()
    s3.client = _client
    s3.bucket = "bucket"
    return s3


def _doc(collection_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), collection_id=collection_id)


def _patch_apis(
    monkeypatch, *, get_by_ids, deleted_per_batch: int, orphans, order_log: list
) -> dict:
    """Patch the data-access APIs the facade calls; record the cross-store call order."""
    qdrant_delete = AsyncMock(side_effect=lambda *a, **k: order_log.append("qdrant"))
    pg_delete = AsyncMock(
        side_effect=lambda *a, **k: (order_log.append("pg_delete"), deleted_per_batch)[1]
    )
    monkeypatch.setattr(df_module.DocumentApi, "get_by_ids", AsyncMock(side_effect=get_by_ids))
    monkeypatch.setattr(df_module.DocumentApi, "delete_many", pg_delete)
    monkeypatch.setattr(df_module.QdrantIndexApi, "delete_by_documents", qdrant_delete)
    monkeypatch.setattr(
        df_module.BlobApi, "collect_hashes_for_documents", AsyncMock(return_value=["h"])
    )
    monkeypatch.setattr(df_module.ArtifactCacheApi, "delete_for_documents", AsyncMock())
    # The guarded purge folds find-unreferenced + delete-rows into one DELETE ... RETURNING that
    # yields exactly the removed hashes (the set fed to the S3 delete).
    monkeypatch.setattr(df_module.BlobApi, "delete_unreferenced", AsyncMock(return_value=orphans))
    monkeypatch.setattr(df_module.S3ObjectApi, "delete_many", AsyncMock())
    monkeypatch.setattr(
        df_module.DatabaseHelpers, "qdrant_collection_name", staticmethod(lambda cid: f"c_{cid}")
    )
    return {"qdrant": qdrant_delete, "pg_delete": pg_delete}


async def _run_delete_many(facade: DocumentsFacade, ids) -> int:
    return await facade.delete_many(ids)


def test_delete_many_processes_in_bounded_batches(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(df_module, "_DELETE_BATCH_SIZE", 2)  # force multi-batch on a small set
    collection = uuid.uuid4()
    docs = [_doc(collection) for _ in range(3)]
    ids = [d.id for d in docs]
    # get_by_ids returns the docs for whichever batch ids it is handed.
    by_id = {d.id: d for d in docs}
    batches: list[list] = []

    def get_by_ids(session, wanted):
        resolved = [by_id[i] for i in wanted]
        batches.append(list(wanted))
        return resolved

    order: list[str] = []
    mocks = _patch_apis(
        monkeypatch, get_by_ids=get_by_ids, deleted_per_batch=None, orphans=["h"], order_log=order
    )
    # deleted_per_batch None → make delete_many return the count of ids it was given.
    mocks["pg_delete"].side_effect = lambda session, live: (order.append("pg_delete"), len(live))[1]

    facade = DocumentsFacade(
        _postgres_yielding(_session_mock()), MagicMock(raw=MagicMock()), _s3_client()
    )
    total = asyncio.run(_run_delete_many(facade, ids))

    # 3 ids, batch size 2 → batches of 2 and 1; every target processed, none dropped.
    assert [len(b) for b in batches] == [2, 1]
    assert total == 3
    # Coherent order within each batch: Qdrant points purged BEFORE the Postgres cascade.
    assert order.index("qdrant") < order.index("pg_delete")


def test_delete_many_deduplicates_ids(monkeypatch) -> None:
    import asyncio

    monkeypatch.setattr(df_module, "_DELETE_BATCH_SIZE", 500)
    collection = uuid.uuid4()
    doc = _doc(collection)
    seen: list[list] = []

    def get_by_ids(session, wanted):
        seen.append(list(wanted))
        return [doc]

    order: list[str] = []
    _patch_apis(
        monkeypatch, get_by_ids=get_by_ids, deleted_per_batch=1, orphans=[], order_log=order
    )
    facade = DocumentsFacade(
        _postgres_yielding(_session_mock()), MagicMock(raw=MagicMock()), _s3_client()
    )

    # The same id three times collapses to one target (one batch, one id).
    asyncio.run(_run_delete_many(facade, [doc.id, doc.id, doc.id]))
    assert seen == [[doc.id]]


def test_delete_many_empty_is_zero_and_touches_nothing(monkeypatch) -> None:
    import asyncio

    order: list[str] = []
    mocks = _patch_apis(
        monkeypatch, get_by_ids=lambda s, w: [], deleted_per_batch=0, orphans=[], order_log=order
    )
    facade = DocumentsFacade(
        _postgres_yielding(_session_mock()), MagicMock(raw=MagicMock()), _s3_client()
    )
    total = asyncio.run(_run_delete_many(facade, []))
    assert total == 0
    mocks["qdrant"].assert_not_awaited()
    mocks["pg_delete"].assert_not_awaited()
