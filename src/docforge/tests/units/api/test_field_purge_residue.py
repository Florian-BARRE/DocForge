"""QdrantFieldPurgeApi.residue — a name the post-change schema still has is NEVER purged (M4).

A swap A↔B or a remove A + rename B→A hands a departed name back to a live field: blanking its payload
key / meta vectors would make its filter match nothing until the backfill repaints. Only true residue
(a departed name not reused, or an indexed key no current field explains) is cleared. Qdrant mocked."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.services.db.qdrant import QdrantFieldPurgeApi
from shared_libs.services.db.qdrant.apis import field_purge_api as fpa_module


def _client(indexed: set[str]) -> SimpleNamespace:
    info = SimpleNamespace(payload_schema={key: object() for key in indexed})
    return SimpleNamespace(get_collection=AsyncMock(return_value=info))


async def _residue(monkeypatch, *, indexed, declared, departed, current):
    monkeypatch.setattr(
        fpa_module.QdrantCollectionApi,
        "declared_vectors",
        AsyncMock(return_value=(set(declared), set())),
    )
    return await QdrantFieldPurgeApi.residue(
        _client(indexed), "c", departed=departed, current=current
    )


async def test_swap_purges_nothing(monkeypatch) -> None:
    keys, indexed, vectors = await _residue(
        monkeypatch,
        indexed={"a", "b"},
        declared={"meta_a_dense", "meta_b_dense"},
        departed=["a", "b"],
        current=["a", "b"],
    )
    assert keys == set() and indexed == set() and vectors == set()


async def test_remove_then_rename_into_purges_only_the_unreused_name(monkeypatch) -> None:
    keys, indexed, vectors = await _residue(
        monkeypatch,
        indexed={"a", "b"},
        declared={"meta_a_dense", "meta_b_dense"},
        departed=["a", "b"],
        current=["a"],
    )
    assert keys == {"b"} and indexed == {"b"} and vectors == {"meta_b_dense"}


async def test_plain_rename_purges_the_old_name_keeps_the_new(monkeypatch) -> None:
    keys, indexed, vectors = await _residue(
        monkeypatch,
        indexed={"a"},
        declared={"meta_a_dense"},
        departed=["a"],
        current=["b"],
    )
    assert keys == {"a"} and indexed == {"a"} and vectors == {"meta_a_dense"}
