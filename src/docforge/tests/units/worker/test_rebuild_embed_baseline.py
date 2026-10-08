"""rebuild_index derives needs_reindex PER AXIS of the indexed embed baseline: a sparse-provider switch
the copy re-encodes clears the flag and advances both baselines; a dense model switch keeps it raised
(a rebuild never re-embeds dense content); a non-IDF sparse endpoint switch (bge A → bge B), which the
store alone cannot see, is re-encoded thanks to the baseline and then cleared. A baseline stamped
before the per-axis split (one whole-space sha256) is still read per axis."""

# ====== Standard Library Imports ======
import copy
import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
import pytest
from qdrant_client import models
from rebuild_qdrant_fake import FakeQdrant, install, postgres
from rebuild_qdrant_fake import facade as _facade

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedLayoutError
from shared_libs.pipelines.nodes.embed.dense_sparse import EmbedDenseSparseNode
from shared_libs.public_models import SparseVector
from shared_libs.services.db.facades.helpers import DatabaseHelpers
from shared_libs.services.db.facades.index_rebuild_payloads import StoreCopyResult
from shared_libs.services.db.facades.index_rebuild_reconciler import IndexRebuildReconciler
from shared_libs.services.db.index_embed_baseline import EmbedBaseline
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.index_signature_embed import EmbedVectorSpace
from shared_libs.services.db.postgresql.apis import ChunkApi, CollectionApi

_BGE = {"kind": "bge_server", "base_url": "http://bge_server:80"}
_OLD_SPARSE = models.SparseVector(indices=[999], values=[9.0])


def _pipeline(dense: dict | None, sparse: dict | None) -> dict:
    """A one-embed-node ingest blob with the given slots."""
    config = {"dense": dense, "sparse": sparse}
    embed = {"kind": "dense_sparse", "family": "embed", "id": "embed", "config": config}
    return {"kind": "group", "id": "root", "nodes": [embed], "transitions": [], "bindings": {}}


def _pre_split(blob: dict) -> str:
    """The whole-space embed baseline format stamped before the per-axis split."""
    canonical = json.dumps(EmbedVectorSpace.canonical(blob), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pre_slots(base_url: str) -> str:
    """The pre-slots whole-space baseline of a stock bge_server (dense + sparse) collection."""
    keys = ("base_url", "model", "embed_sparse", "embed_semantic_fields")
    legacy = [("embed", "bge_server", tuple(zip(keys, (base_url, None, None, None), strict=True)))]
    return hashlib.sha256(json.dumps(legacy, default=str).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# EmbedBaseline — per-axis comparison
# --------------------------------------------------------------------------- #
BGE_BOTH = _pipeline(_BGE, _BGE)
BM25 = _pipeline(_BGE, {"kind": "bm25_local"})
OTHER_DENSE = _pipeline({**_BGE, "model": "other-model"}, {"kind": "bm25_local"})


@pytest.mark.parametrize(
    "stored",
    [
        EmbedBaseline.signature(BGE_BOTH),
        _pre_split(BGE_BOTH),
        _pre_slots("http://bge_server:80"),
    ],
    ids=["per-axis", "pre-split", "pre-slots"],
)
def test_a_sparse_switch_keeps_the_dense_half(stored: str) -> None:
    assert EmbedBaseline.dense_matches(stored, BM25)
    assert not EmbedBaseline.sparse_matches(stored, BM25)
    assert not EmbedBaseline.dense_matches(stored, OTHER_DENSE)
    assert EmbedBaseline.dense_matches(stored, BGE_BOTH)
    assert EmbedBaseline.sparse_matches(stored, BGE_BOTH)


def test_the_per_axis_signature_fits_the_column_and_is_a_candidate() -> None:
    signature = CollectionIndexSignature.embed_signature(BGE_BOTH)
    assert len(signature) == 64 and ":" in signature
    assert signature in CollectionIndexSignature.embed_candidates(BGE_BOTH)
    assert not EmbedBaseline.dense_matches(None, BGE_BOTH)


# --------------------------------------------------------------------------- #
# IndexRebuildReconciler._derive_flag
# --------------------------------------------------------------------------- #
def _stub_collection(monkeypatch, pipeline: dict, stored: str | None) -> AsyncMock:
    collection = SimpleNamespace(
        pipeline=pipeline, indexed_embed_signature=stored, needs_reindex=True
    )
    monkeypatch.setattr(CollectionApi, "get", staticmethod(AsyncMock(return_value=collection)))
    monkeypatch.setattr(CollectionApi, "get_schema", staticmethod(AsyncMock(return_value=[])))
    update = AsyncMock()
    monkeypatch.setattr(CollectionApi, "update", staticmethod(update))
    return update


def _reconciler() -> IndexRebuildReconciler:
    return IndexRebuildReconciler(postgres(), SimpleNamespace(raw="raw"), index_state=None)


@pytest.mark.parametrize(
    "stored", [EmbedBaseline.signature(BGE_BOTH), _pre_slots("http://bge_server:80")]
)
async def test_bge_to_bm25_local_rebuild_clears_and_advances_baselines(monkeypatch, stored) -> None:
    update = _stub_collection(monkeypatch, BM25, stored)

    flag, dense_changed = await _reconciler()._derive_flag(uuid.uuid4(), False, True)

    assert (flag, dense_changed) == (False, False)
    kwargs = update.await_args.kwargs
    assert kwargs["needs_reindex"] is False
    assert kwargs["indexed_embed_signature"] == EmbedBaseline.signature(BM25)
    assert kwargs["indexed_signature"] == CollectionIndexSignature.compute(BM25, [])


async def test_sparse_switch_without_reencode_keeps_the_flag(monkeypatch) -> None:
    update = _stub_collection(monkeypatch, BM25, EmbedBaseline.signature(BGE_BOTH))

    flag, _ = await _reconciler()._derive_flag(uuid.uuid4(), False, False)

    assert flag is True
    update.assert_not_awaited()


async def test_dense_model_switch_keeps_the_flag_raised(monkeypatch) -> None:
    update = _stub_collection(monkeypatch, OTHER_DENSE, EmbedBaseline.signature(BGE_BOTH))

    flag, dense_changed = await _reconciler()._derive_flag(uuid.uuid4(), False, True)

    assert (flag, dense_changed) == (True, True)
    assert update.await_args.kwargs == {"needs_reindex": True}


async def test_unknown_baseline_keeps_the_stored_flag(monkeypatch) -> None:
    update = _stub_collection(monkeypatch, BM25, None)

    flag, _ = await _reconciler()._derive_flag(uuid.uuid4(), False, True)

    assert flag is True
    update.assert_not_awaited()


# --------------------------------------------------------------------------- #
# StoreRebuildFacade — a non-IDF sparse endpoint switch is re-encoded
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake(monkeypatch) -> FakeQdrant:
    return install(monkeypatch)


async def test_bge_a_to_bge_b_sparse_switch_is_reencoded_then_cleared(monkeypatch, fake) -> None:
    # 1. Indexed with bge A on both slots; the sparse slot now points at bge B (same modifier).
    indexed = _pipeline(_BGE, _BGE)
    current = copy.deepcopy(indexed)
    current["nodes"][0]["config"]["sparse"] = {"kind": "bge_server", "base_url": "http://bge-b:80"}
    collection_id, point_id = uuid.uuid4(), str(uuid.uuid4())
    stable = DatabaseHelpers.qdrant_collection_name(collection_id)
    record = models.Record(
        id=point_id,
        payload={"document_id": "d1"},
        vector={"content_dense": [0.1] * 4, "content_bm25": _OLD_SPARSE},
    )
    fake.add(stable, {"content_dense"}, {"content_bm25"}, [record])
    collection = SimpleNamespace(
        pipeline=current,
        indexed_embed_signature=EmbedBaseline.signature(indexed),
        needs_reindex=True,
    )
    monkeypatch.setattr(CollectionApi, "get", staticmethod(AsyncMock(return_value=collection)))
    chunk = SimpleNamespace(id=uuid.UUID(point_id), text="Passation des marchés")
    monkeypatch.setattr(ChunkApi, "get_by_ids", staticmethod(AsyncMock(return_value=[chunk])))
    sparse = AsyncMock(return_value=[SparseVector(indices=[3], values=[0.5])])
    monkeypatch.setattr(EmbedDenseSparseNode, "_embed_sparse", sparse)

    # 2. The copy re-encodes content sparse through bge B (the store alone cannot see the switch).
    result = await _facade(fake).rebuild(collection_id, batch_size=10)

    assert result.sparse_reencoded and result.reencoded_sparse_points == 1
    [point] = fake.collections[result.physical]["points"]
    assert point.vector["content_bm25"].indices == [3]

    # 3. The reconcile then clears the flag.
    update = _stub_collection(monkeypatch, current, collection.indexed_embed_signature)
    flag, _ = await _reconciler()._derive_flag(collection_id, False, result.sparse_reencoded)
    assert flag is False
    assert update.await_args.kwargs["indexed_embed_signature"] == EmbedBaseline.signature(current)


def test_store_copy_result_defaults_to_no_reencode() -> None:
    assert StoreCopyResult(physical=None).sparse_reencoded is False


async def test_a_broken_embed_blob_fails_the_rebuild_before_any_schema(monkeypatch, fake) -> None:
    """The rebuild CREATES a store schema: a non-building embed node fails fast (strict layout),
    never a guessed default layout — and the old store stays live."""
    collection_id = uuid.uuid4()
    stable = DatabaseHelpers.qdrant_collection_name(collection_id)
    fake.add(stable, {"content_dense"}, {"content_bm25"}, [])
    broken = _pipeline({"kind": "removed_provider", "api_key": "sk-REALSECRET"}, None)
    collection = SimpleNamespace(pipeline=broken, indexed_embed_signature=None)
    monkeypatch.setattr(CollectionApi, "get", staticmethod(AsyncMock(return_value=collection)))

    with pytest.raises(EmbedLayoutError) as caught:
        await _facade(fake).rebuild(collection_id, batch_size=10)

    assert "embed node 'embed'" in str(caught.value) and "REALSECRET" not in str(caught.value)
    assert list(fake.collections) == [stable]
