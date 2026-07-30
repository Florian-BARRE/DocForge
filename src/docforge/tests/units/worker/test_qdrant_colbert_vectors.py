"""ColBERT third named vector — the persistence/data-layer side (Wave 1).

Proves the vector-layer symbols have real consumers: ``colbert_config`` builds the int8 + on_disk
MAX_SIM multi-vector params, ``QdrantIndexApi._to_struct`` merges ``QdrantPoint.multivector`` into
the qdrant named-vector dict, and ``QdrantCollectionApi.ensure`` declares ``content_colbert`` only
when a ``colbert_dim`` is passed. Qdrant client is faked — no live store."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from qdrant_client import models

from shared_libs.services.db.qdrant import (
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    QdrantVectorSchema,
    SparseVec,
    VectorNames,
)


def test_colbert_config_is_int8_on_disk_max_sim() -> None:
    config = QdrantVectorSchema.colbert_config(dim=128)
    params = config[VectorNames.CONTENT_COLBERT]
    assert params.size == 128
    assert params.distance == models.Distance.COSINE
    assert params.on_disk is True
    assert params.multivector_config.comparator == models.MultiVectorComparator.MAX_SIM
    assert params.quantization_config.scalar.type == models.ScalarType.INT8
    assert params.quantization_config.scalar.always_ram is False


def test_to_struct_merges_multivector_into_the_named_vector_dict() -> None:
    point = QdrantPoint(
        point_id="p0",
        payload={"document_id": "d"},
        dense={VectorNames.CONTENT_DENSE: [1.0, 2.0]},
        sparse={VectorNames.CONTENT_SPARSE: SparseVec(indices=[3], values=[0.5])},
        multivector={VectorNames.CONTENT_COLBERT: [[0.1, 0.2], [0.3, 0.4]]},
    )
    struct = QdrantIndexApi._to_struct(point)
    # The three vector spaces share ONE named-vector dict handed to qdrant-client.
    assert struct.vector[VectorNames.CONTENT_DENSE] == [1.0, 2.0]
    assert struct.vector[VectorNames.CONTENT_COLBERT] == [[0.1, 0.2], [0.3, 0.4]]
    assert isinstance(struct.vector[VectorNames.CONTENT_SPARSE], models.SparseVector)


def test_to_struct_omits_colbert_when_multivector_empty() -> None:
    point = QdrantPoint(point_id="p0", payload={}, dense={VectorNames.CONTENT_DENSE: [1.0]})
    struct = QdrantIndexApi._to_struct(point)
    assert VectorNames.CONTENT_COLBERT not in struct.vector


async def test_ensure_declares_colbert_only_when_dim_given() -> None:
    """ensure threads colbert_dim into create_collection's vectors_config, and skips it when None."""
    client = SimpleNamespace(
        collection_exists=AsyncMock(return_value=False),
        create_collection=AsyncMock(),
        create_payload_index=AsyncMock(),
    )
    # 1. With a colbert_dim, the content_colbert multi-vector is declared.
    await QdrantCollectionApi.ensure(client, "c1", dense_dim=8, colbert_dim=64)
    with_colbert = client.create_collection.await_args.kwargs["vectors_config"]
    assert VectorNames.CONTENT_COLBERT in with_colbert
    assert with_colbert[VectorNames.CONTENT_COLBERT].size == 64

    # 2. Without it, no ColBERT vector is declared.
    client.create_collection.reset_mock()
    await QdrantCollectionApi.ensure(client, "c2", dense_dim=8)
    without_colbert = client.create_collection.await_args.kwargs["vectors_config"]
    assert VectorNames.CONTENT_COLBERT not in without_colbert


async def test_upsert_splits_oversized_colbert_into_multiple_requests() -> None:
    """A whole-document ColBERT upsert past the byte budget is split, so no single request can trip
    Qdrant's 32 MB max_request_size (real full-precision colbert floats cross it in ~6 chunks)."""
    upsert = AsyncMock()
    client = SimpleNamespace(upsert=upsert)
    # ~9 MB/point (400 tokens x 1024 dims x ~22 bytes) → two points exceed the 16 MB budget.
    big = [[0.0] * 1024 for _ in range(400)]
    points = [
        QdrantPoint(
            point_id=f"p{i}",
            payload={},
            dense={VectorNames.CONTENT_DENSE: [0.0] * 1024},
            multivector={VectorNames.CONTENT_COLBERT: big},
        )
        for i in range(2)
    ]
    await QdrantIndexApi.upsert(client, "col", points)
    assert upsert.await_count == 2  # split into per-point requests, not one oversized body
    for call in upsert.await_args_list:
        assert len(call.kwargs["points"]) == 1


async def test_upsert_keeps_small_batch_as_one_request() -> None:
    """Small (dense-only) points stay a single request — batching only bites when bytes are large."""
    upsert = AsyncMock()
    client = SimpleNamespace(upsert=upsert)
    points = [
        QdrantPoint(point_id=f"p{i}", payload={}, dense={VectorNames.CONTENT_DENSE: [0.0] * 8})
        for i in range(50)
    ]
    await QdrantIndexApi.upsert(client, "col", points)
    assert upsert.await_count == 1
    assert len(upsert.await_args.kwargs["points"]) == 50
