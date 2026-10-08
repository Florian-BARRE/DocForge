"""rebuild_index data-safety: the stranded-generation self-heal, the generation settle rules, the swap
cleanup paths, and the own-row abort between copy batches — all against the in-memory fake Qdrant.
"""

# ====== Standard Library Imports ======
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from rebuild_qdrant_fake import FakeQdrant, facade, install, record

from shared_libs.public_models import FieldScope

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    RebuildCancelledError,
    SearchFacade,
    StoreCopyResult,
)
from shared_libs.services.db.facades.helpers import DatabaseHelpers
from shared_libs.services.db.facades.index_rebuild_reconciler import IndexRebuildReconciler
from shared_libs.services.db.facades.transfer_facade import CollectionTransferFacade
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import QdrantAliasApi, QdrantCollectionApi

_V = ({"content_dense"}, {"content_bm25"})


@pytest.fixture
def stable() -> str:
    return DatabaseHelpers.qdrant_collection_name(uuid.uuid4())


@pytest.fixture
def fake(monkeypatch) -> FakeQdrant:
    return install(monkeypatch)


def _cid(stable: str) -> uuid.UUID:
    return uuid.UUID(stable.removeprefix("col_"))


async def test_stranded_complete_generation_is_adopted_by_ensure(fake, stable, monkeypatch):
    fake.add(f"{stable}_r7", *_V, [record(1, "d1")], complete=True)
    monkeypatch.undo()  # the REAL ensure: it must adopt, never create an empty physical store

    await QdrantCollectionApi.ensure(fake, stable, dense_dim=4)

    assert fake.aliases == {stable: f"{stable}_r7"}
    assert stable not in fake.collections


async def test_partial_generation_is_never_adopted(fake, stable):
    fake.add(f"{stable}_r7", *_V, [record(1, "d1")])

    assert await QdrantAliasApi.resolve_or_adopt(fake, stable) is False
    assert fake.aliases == {}


async def test_search_and_export_adopt_the_stranded_generation(fake, stable):
    fake.add(f"{stable}_r7", *_V, [record(1, "d1")], complete=True)
    qdrant = SimpleNamespace(raw=fake)

    # Export reads the dense dim through the alias (would ship 0 points before the heal).
    transfer = CollectionTransferFacade.__new__(CollectionTransferFacade)
    transfer._qdrant = qdrant
    assert await transfer.dense_dim(_cid(stable)) == 4
    assert fake.aliases == {stable: f"{stable}_r7"}
    # Search sees the store too (the existence gate is the healing one).
    fake.aliases.clear()
    keys = await SearchFacade(MagicMock(), qdrant).bm25_meta_vectors(_cid(stable))
    assert fake.aliases == {stable: f"{stable}_r7"} and isinstance(keys, set)


async def test_physical_store_wins_over_a_stamped_generation(fake, stable):
    """A physical stable store next to a stamped copy survived a swap that never completed: it is
    the truth (even when EMPTY — all documents deleted), so the stale copy is dropped, never adopted
    (adopting it would resurrect deleted documents' points)."""
    fake.add(stable, *_V, [])
    fake.add(f"{stable}_r7", *_V, [record(1, "d1")], complete=True)

    result = await facade(fake).rebuild(_cid(stable), batch_size=10)

    assert result.copied_points == 0
    assert result.first_rebuild is True
    assert f"{stable}_r7" not in fake.collections
    assert fake.aliases == {stable: result.physical}


async def test_cancel_mid_copy_aborts_pre_swap_and_drops_temp(fake, stable):
    fake.add(stable, *_V, [record(1, "d1"), record(2, "d2")])
    probes = iter([False, True])

    with pytest.raises(RebuildCancelledError):
        await facade(fake).rebuild(_cid(stable), 1, should_abort=AsyncMock(side_effect=probes))

    assert list(fake.collections) == [stable] and fake.aliases == {}


async def test_first_swap_alias_is_retried(fake, stable):
    fake.add(stable, *_V, [record(1, "d1")])
    fake.alias_failures = 2

    result = await facade(fake).rebuild(_cid(stable), batch_size=10)

    assert fake.aliases == {stable: result.physical}


async def test_first_swap_alias_exhausted_keeps_the_stamped_copy_adoptable(fake, stable):
    fake.add(stable, *_V, [record(1, "d1")])
    fake.alias_failures = 99

    with pytest.raises(RuntimeError, match="alias exploded"):
        await facade(fake).rebuild(_cid(stable), batch_size=10)

    # The original is gone but the stamped copy survives; the next access re-adopts it.
    (temp,) = list(fake.collections)
    fake.alias_failures = 0
    assert await QdrantAliasApi.resolve_or_adopt(fake, stable)
    assert fake.aliases == {stable: temp}


async def test_first_swap_failed_delete_keeps_temp_then_next_rebuild_settles_it(fake, stable):
    """A failed delete may still complete server-side, so the stamped temp is never dropped there;
    with the old store surviving, the next rebuild's settle drops it and the old store stays truth."""
    fake.add(stable, *_V, [record(1, "d1")])
    fake.fail_delete = True

    with pytest.raises(RuntimeError, match="delete exploded"):
        await facade(fake).rebuild(_cid(stable), batch_size=10)

    fake.fail_delete = False
    leftovers = [name for name in fake.collections if name != stable]
    assert stable in fake.collections and fake.aliases == {} and len(leftovers) == 1

    result = await facade(fake).rebuild(_cid(stable), batch_size=10)

    assert result.copied_points == 1
    assert leftovers[0] not in fake.collections
    assert fake.aliases == {stable: result.physical}


async def test_chunk_semantic_vector_nobody_carries_keeps_needs_reindex(monkeypatch):
    field = SimpleNamespace(field_name="topic", scope=FieldScope.CHUNK, semantic=True)
    monkeypatch.setattr(CollectionApi, "get_schema", staticmethod(AsyncMock(return_value=[field])))
    rebuild = IndexRebuildReconciler(MagicMock(), MagicMock(), index_state=None)
    rebuild._postgres = SimpleNamespace(session=_session)
    copy = StoreCopyResult(physical="x", copied_points=3, carried_vectors={"content_dense"})

    assert await rebuild._unfilled_chunk_fields(uuid.uuid4(), copy) == ["topic"]
    copy.carried_vectors.add("meta_topic_dense")
    assert await rebuild._unfilled_chunk_fields(uuid.uuid4(), copy) == []


class _session:
    """A no-op async session context."""

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False
