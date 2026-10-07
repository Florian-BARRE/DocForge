"""The Qdrant half of rebuild_index against an in-memory fake Qdrant (aliases + collections + points).

Covers StoreRebuildFacade (copy drops every ``meta_*_bm25`` vector; a pre-swap failure drops the temp
and leaves the old store live; first swap = delete + create alias, later swap = atomic alias re-point +
drop the old physical; a generation stranded by a crashed first swap is re-adopted), QdrantAliasApi
drop (resolves alias → physical and deletes it + every leftover generation) and the reconciliation's
vanished-document purge.
"""

# ====== Standard Library Imports ======
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from rebuild_qdrant_fake import FakeQdrant, install, postgres
from rebuild_qdrant_fake import facade as _facade
from rebuild_qdrant_fake import record as _record

# ====== Internal Project Imports ======
from shared_libs.services.db.facades.helpers import DatabaseHelpers
from shared_libs.services.db.facades.index_rebuild_facade import IndexRebuildFacade
from shared_libs.services.db.postgresql.apis import RebuildJobApi
from shared_libs.services.db.qdrant import QdrantAliasApi, QdrantCollectionApi, QdrantIndexApi


@pytest.fixture
def collection_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def stable(collection_id) -> str:
    return DatabaseHelpers.qdrant_collection_name(collection_id)


@pytest.fixture
def fake(monkeypatch) -> FakeQdrant:
    return install(monkeypatch)


async def test_first_rebuild_copies_drops_meta_bm25_and_aliases(fake, stable, collection_id):
    fake.add(stable, {"content_dense"}, {"content_bm25"}, [_record(1, "d1"), _record(2, "d2")])

    result = await _facade(fake).rebuild(collection_id, batch_size=1)

    assert result.first_rebuild is True
    assert result.copied_points == 2
    assert result.document_ids == {"d1", "d2"}
    # The original physical store is gone; the stable name is now an alias onto the new generation.
    assert stable not in fake.collections
    assert fake.aliases == {stable: result.physical}
    copied = fake.collections[result.physical]["points"]
    for point in copied:
        # meta_*_bm25 dropped (re-encoded by the backfill); undeclared vectors dropped; content kept.
        assert set(point.vector) == {"content_dense", "content_bm25"}
    # Stamped complete BEFORE the non-atomic first swap (delete the physical, then the alias).
    stamp = fake.calls.index(("update_collection", result.physical))
    assert stamp < fake.calls.index(("delete_collection", stable))
    assert fake.calls.index(("delete_collection", stable)) < fake.calls.index(("update_aliases", 1))
    assert await QdrantAliasApi.is_complete(fake, result.physical)


async def test_later_rebuild_swaps_alias_atomically_then_drops_old(fake, stable, collection_id):
    old = f"{stable}_r100"
    fake.add(old, {"content_dense"}, {"content_bm25"}, [_record(1, "d1")])
    fake.aliases[stable] = old

    result = await _facade(fake).rebuild(collection_id, batch_size=10)

    assert result.first_rebuild is False
    assert fake.aliases == {stable: result.physical}
    assert old not in fake.collections
    # One request carrying delete + create alias, THEN the old physical collection is dropped.
    swap = fake.calls.index(("update_aliases", 2))
    assert swap < fake.calls.index(("delete_collection", old))


async def test_pre_swap_failure_drops_temp_and_keeps_old(fake, stable, collection_id):
    fake.add(stable, {"content_dense"}, {"content_bm25"}, [_record(1, "d1")])
    fake.fail_upsert = True

    with pytest.raises(RuntimeError, match="upsert exploded"):
        await _facade(fake).rebuild(collection_id, batch_size=10)

    # Only the untouched original remains, still physical under the stable name, no alias.
    assert list(fake.collections) == [stable]
    assert fake.aliases == {}
    assert len(fake.collections[stable]["points"]) == 1


async def test_no_space_is_a_noop(fake, collection_id):
    result = await _facade(fake).rebuild(collection_id, batch_size=10)

    assert result.physical is None
    assert fake.collections == {}


async def test_stranded_generation_is_readopted(fake, stable, collection_id):
    # A first swap crashed after deleting the original: the data lives in an un-aliased, stamped
    # generation; a newer PARTIAL copy (unstamped) must never be the one adopted.
    fake.add(f"{stable}_r5", {"content_dense"}, {"content_bm25"}, [_record(1, "d1")], complete=True)
    fake.add(f"{stable}_r9", {"content_dense"}, {"content_bm25"}, [])

    result = await _facade(fake).rebuild(collection_id, batch_size=10)

    assert result.copied_points == 1
    assert fake.aliases == {stable: result.physical}
    assert list(fake.collections) == [result.physical]


async def test_drop_resolves_alias_and_deletes_physical_and_leftovers(fake, stable):
    fake.add(f"{stable}_r100", set(), set(), [])
    fake.add(f"{stable}_r50", set(), set(), [])
    fake.aliases[stable] = f"{stable}_r100"

    await QdrantCollectionApi.drop(fake, stable)

    assert fake.collections == {}
    assert fake.aliases == {}
    # The alias NAME itself is never "deleted" (a silent no-op in Qdrant).
    assert ("delete_collection", stable) not in fake.calls


async def test_drop_of_a_never_rebuilt_collection(fake, stable):
    fake.add(stable, set(), set(), [])

    await QdrantCollectionApi.drop(fake, stable)

    assert fake.collections == {}


async def test_reconcile_purges_points_of_vanished_documents(monkeypatch, collection_id):
    alive, gone = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        RebuildJobApi, "document_ids", staticmethod(AsyncMock(return_value={alive}))
    )
    delete = AsyncMock()
    monkeypatch.setattr(QdrantIndexApi, "delete_by_documents", staticmethod(delete))
    facade = IndexRebuildFacade(postgres(), SimpleNamespace(raw="raw"), index_state=None)

    removed = await facade._purge_vanished(collection_id, "col_x", {str(alive), str(gone)})

    assert removed == 1
    delete.assert_awaited_once_with("raw", "col_x", [gone])
