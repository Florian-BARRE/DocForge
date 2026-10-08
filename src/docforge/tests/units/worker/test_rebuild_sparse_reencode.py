"""rebuild_index re-encodes the content sparse vector when the old store's one came from ANOTHER sparse
provider (IDF modifier disagreeing with the config) or is absent while the config has a sparse slot:
the copy drops it and writes the vector re-encoded from the Postgres chunk text in the same upsert.
A store whose content sparse vector matches the config keeps it verbatim (no provider call)."""

# ====== Standard Library Imports ======
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from qdrant_client import models
from rebuild_qdrant_fake import FakeQdrant, install, postgres
from rebuild_qdrant_fake import facade as _facade

# ====== Internal Project Imports ======
from shared_libs.public_models import SparseVector, VectorLayout
from shared_libs.services.db.facades.content_sparse_reencoder import ContentSparseReencoder
from shared_libs.services.db.facades.helpers import DatabaseHelpers
from shared_libs.services.db.postgresql.apis import ChunkApi, CollectionApi
from shared_libs.services.db.qdrant import DeclaredVectors, QdrantStoreCopyApi, SparseVec

_BM25_LAYOUT = VectorLayout(sparse_idf=True)
_OLD_SPARSE = models.SparseVector(indices=[999], values=[9.0])


def _pipeline(sparse: dict | None) -> dict:
    """An ingest blob whose dense_sparse embedder has a bge dense slot and the given sparse slot."""
    config = {"dense": {"kind": "bge_server", "base_url": "http://bge:80"}, "sparse": sparse}
    embed = {"kind": "dense_sparse", "family": "embed", "id": "embed", "config": config}
    return {"kind": "group", "id": "root", "nodes": [embed], "transitions": [], "bindings": {}}


def _record(point_id: str) -> models.Record:
    return models.Record(
        id=point_id,
        payload={"document_id": "d1"},
        vector={"content_dense": [0.1] * 4, "content_bm25": _OLD_SPARSE},
    )


# --------------------------------------------------------------------------- #
# QdrantStoreCopyApi — dropped + re-encoded vectors
# --------------------------------------------------------------------------- #
def test_keep_vector_drops_meta_bm25_undeclared_and_explicitly_dropped() -> None:
    declared = {"content_dense", "content_bm25", "meta_x_bm25"}
    assert QdrantStoreCopyApi.keep_vector("content_bm25", declared)
    assert not QdrantStoreCopyApi.keep_vector("content_bm25", declared, {"content_bm25"})
    assert not QdrantStoreCopyApi.keep_vector("meta_x_bm25", declared)
    assert not QdrantStoreCopyApi.keep_vector("legacy", declared)


def test_to_points_replaces_a_dropped_content_sparse_with_the_reencoded_one() -> None:
    point_id = str(uuid.uuid4())
    extra = {point_id: {"content_bm25": SparseVec(indices=[1, 2], values=[0.5, 0.25])}}
    [point] = QdrantStoreCopyApi.to_points(
        [_record(point_id)], {"content_dense", "content_bm25"}, {"content_bm25"}, extra
    )
    assert point.vector["content_bm25"].indices == [1, 2]
    assert "content_dense" in point.vector


# --------------------------------------------------------------------------- #
# ContentSparseReencoder
# --------------------------------------------------------------------------- #
def test_reencode_needed_only_for_a_mismatched_or_absent_content_sparse() -> None:
    plain = DeclaredVectors(dense=frozenset({"content_dense"}), sparse=frozenset({"content_bm25"}))
    idf = DeclaredVectors(
        sparse=frozenset({"content_bm25"}), idf_sparse=frozenset({"content_bm25"})
    )
    dense_only = DeclaredVectors(dense=frozenset({"content_dense"}))
    assert not ContentSparseReencoder.needed(plain, VectorLayout())  # bge → bge: copy
    assert ContentSparseReencoder.needed(plain, _BM25_LAYOUT)  # bge vectors under bm25_local
    assert ContentSparseReencoder.needed(idf, VectorLayout())  # bm25 vectors under bge
    assert not ContentSparseReencoder.needed(idf, _BM25_LAYOUT)
    assert ContentSparseReencoder.needed(dense_only, VectorLayout())  # sparse slot switched on
    assert not ContentSparseReencoder.needed(dense_only, VectorLayout(sparse=False))


async def test_encode_reads_chunk_text_batches_and_skips_orphans_and_termless(monkeypatch) -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    chunks = [SimpleNamespace(id=ids[0], text="alpha"), SimpleNamespace(id=ids[1], text="")]
    monkeypatch.setattr(ChunkApi, "get_by_ids", staticmethod(AsyncMock(return_value=chunks)))

    async def _sparse(texts: list[str]) -> list[SparseVector]:
        return [SparseVector(indices=[7] if t else [], values=[1.0] if t else []) for t in texts]

    embedder = SimpleNamespace(
        config=SimpleNamespace(batch_size=1), _embed_sparse=AsyncMock(side_effect=_sparse)
    )
    reencoder = ContentSparseReencoder(postgres(), embedder)  # type: ignore[arg-type]

    encoded = await reencoder.encode([str(i) for i in ids])

    assert encoded == {str(ids[0]): {"content_bm25": SparseVec(indices=[7], values=[1.0])}}
    assert embedder._embed_sparse.await_count == 2  # batch_size 1, the orphan (ids[2]) never sent


# --------------------------------------------------------------------------- #
# StoreRebuildFacade wiring
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake(monkeypatch) -> FakeQdrant:
    return install(monkeypatch)


async def _rebuild(monkeypatch, fake: FakeQdrant, sparse: dict | None, texts: dict[str, str]):
    collection_id = uuid.uuid4()
    stable = DatabaseHelpers.qdrant_collection_name(collection_id)
    fake.add(stable, {"content_dense"}, {"content_bm25"}, [_record(i) for i in texts])
    collection = SimpleNamespace(pipeline=_pipeline(sparse))
    monkeypatch.setattr(CollectionApi, "get", staticmethod(AsyncMock(return_value=collection)))
    chunks = [SimpleNamespace(id=uuid.UUID(i), text=t) for i, t in texts.items()]
    get_by_ids = AsyncMock(return_value=chunks)
    monkeypatch.setattr(ChunkApi, "get_by_ids", staticmethod(get_by_ids))
    result = await _facade(fake).rebuild(collection_id, batch_size=10)
    return result, fake.collections[result.physical]["points"], get_by_ids


async def test_rebuild_reencodes_bge_content_sparse_under_a_bm25_local_config(
    monkeypatch, fake
) -> None:
    texts = {str(uuid.uuid4()): "Passation des marchés", str(uuid.uuid4()): "Exécution"}
    result, points, get_by_ids = await _rebuild(monkeypatch, fake, {"kind": "bm25_local"}, texts)

    assert result.reencoded_sparse_points == 2
    assert get_by_ids.await_count == 1
    for point in points:
        assert point.vector["content_bm25"].indices != _OLD_SPARSE.indices  # re-encoded
        assert "content_dense" in point.vector  # dense copied verbatim


async def test_rebuild_copies_a_matching_content_sparse_verbatim(monkeypatch, fake) -> None:
    texts = {str(uuid.uuid4()): "text"}
    bge = {"kind": "bge_server", "base_url": "http://bge:80"}
    result, points, get_by_ids = await _rebuild(monkeypatch, fake, bge, texts)

    assert result.reencoded_sparse_points == 0
    get_by_ids.assert_not_awaited()
    assert points[0].vector["content_bm25"] == _OLD_SPARSE
