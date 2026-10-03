"""QdrantIndexApi write batching: every whole-document write path splits into byte-bounded batches so
no single request crosses Qdrant's ~32 MB body limit. upsert already did; update_vectors (the post-hoc
meta-vector sync) previously sent ALL points in one request and 400'd on a large document, silently
breaking the sync; set_payload chunks its per-point operations by count. A fake client records the
batches — no Qdrant."""

import uuid
from typing import Any

from shared_libs.services.db.qdrant.apis import QdrantIndexApi
from shared_libs.services.db.qdrant.vectors import QdrantPoint

# Each point's dense vector is ~8.8 MB estimated (400k floats x 22 bytes), so any two together exceed
# the 16 MB flush threshold — one point per batch, a clean multiplier to assert against.
_BIG_DENSE = 400_000


class _FakeClient:
    """Records the point-count of every write call so batching can be asserted."""

    def __init__(self) -> None:
        self.upserts: list[int] = []
        self.vector_updates: list[int] = []
        self.payload_ops: list[int] = []

    async def upsert(self, *, collection_name: str, points: list) -> None:
        self.upserts.append(len(points))

    async def update_vectors(self, *, collection_name: str, points: list) -> None:
        self.vector_updates.append(len(points))

    async def batch_update_points(self, *, collection_name: str, update_operations: list) -> None:
        self.payload_ops.append(len(update_operations))


def _big_point(pid: str) -> QdrantPoint:
    return QdrantPoint(
        point_id=pid, payload={"document_id": "d"}, dense={"content_dense": [0.0] * _BIG_DENSE}
    )


def _small_point(pid: str, *, with_vectors: bool = True) -> QdrantPoint:
    dense: dict[str, Any] = {"content_dense": [0.1, 0.2]} if with_vectors else {}
    return QdrantPoint(point_id=pid, payload={"document_id": "d"}, dense=dense)


async def test_upsert_splits_large_documents_into_byte_bounded_batches() -> None:
    client = _FakeClient()
    points = [_big_point(f"p{i}") for i in range(3)]
    await QdrantIndexApi.upsert(client, "col", points)  # type: ignore[arg-type]
    # Each ~8.8 MB point exceeds half the 16 MB budget, so no two share a request.
    assert client.upserts == [1, 1, 1]


async def test_upsert_empty_input_makes_no_request() -> None:
    client = _FakeClient()
    await QdrantIndexApi.upsert(client, "col", [])  # type: ignore[arg-type]
    assert client.upserts == []


async def test_update_vectors_batches_large_documents() -> None:
    client = _FakeClient()
    points = [_big_point(f"p{i}") for i in range(3)]
    await QdrantIndexApi.update_vectors(client, "col", points)  # type: ignore[arg-type]
    # The fix: multiple bounded requests instead of one oversized 400-ing request.
    assert client.vector_updates == [1, 1, 1]


async def test_update_vectors_small_document_is_one_request() -> None:
    client = _FakeClient()
    await QdrantIndexApi.update_vectors(  # type: ignore[arg-type]
        client, "col", [_small_point("a"), _small_point("b")]
    )
    assert client.vector_updates == [2]


async def test_update_vectors_skips_points_with_no_vectors() -> None:
    client = _FakeClient()
    points = [_small_point("a"), _small_point("b", with_vectors=False), _small_point("c")]
    await QdrantIndexApi.update_vectors(client, "col", points)  # type: ignore[arg-type]
    # The vectorless point is dropped (an empty named-vector update is invalid), the other two ride.
    assert client.vector_updates == [2]


async def test_set_payload_chunks_operations_by_count() -> None:
    client = _FakeClient()
    payloads = {f"id-{i}": {"topic": "x"} for i in range(2001)}
    await QdrantIndexApi.set_payload(client, "col", payloads)  # type: ignore[arg-type]
    # 2001 ops over a 2000-op cap → two requests (2000 + 1), never one giant batch.
    assert client.payload_ops == [2000, 1]


# -------------------- delete_payload / delete_vectors (metadata-clear primitives) --------------------
class _FakeDeleteClient:
    """Records the delete_payload / delete_vectors calls; drives the collection-exists guard."""

    def __init__(self, *, exists: bool = True) -> None:
        self._exists = exists
        self.payload_deletes: list[dict[str, Any]] = []
        self.vector_deletes: list[dict[str, Any]] = []

    async def collection_exists(self, name: str) -> bool:
        return self._exists

    async def delete_payload(self, *, collection_name: str, keys: list, points: Any) -> None:
        self.payload_deletes.append({"keys": keys, "points": points})

    async def delete_vectors(self, *, collection_name: str, vectors: list, points: Any) -> None:
        self.vector_deletes.append({"vectors": vectors, "points": points})


async def test_delete_payload_filters_on_document_and_passes_keys() -> None:
    client = _FakeDeleteClient()
    doc_id = uuid.uuid4()
    await QdrantIndexApi.delete_payload(client, "col", ["topic", "year"], doc_id)  # type: ignore[arg-type]
    assert len(client.payload_deletes) == 1
    call = client.payload_deletes[0]
    assert call["keys"] == ["topic", "year"]
    # The selector filters on the document_id payload (a Filter, not a raw id list).
    assert str(doc_id) in str(call["points"])


async def test_delete_payload_noops_on_empty_keys_or_missing_collection() -> None:
    present = _FakeDeleteClient()
    await QdrantIndexApi.delete_payload(present, "col", [], uuid.uuid4())  # type: ignore[arg-type]
    assert present.payload_deletes == []

    absent = _FakeDeleteClient(exists=False)
    await QdrantIndexApi.delete_payload(absent, "col", ["topic"], uuid.uuid4())  # type: ignore[arg-type]
    assert absent.payload_deletes == []


async def test_delete_vectors_filters_on_document_and_passes_names() -> None:
    client = _FakeDeleteClient()
    doc_id = uuid.uuid4()
    await QdrantIndexApi.delete_vectors(  # type: ignore[arg-type]
        client, "col", ["meta_abstract_dense", "meta_abstract_bm25"], doc_id
    )
    assert len(client.vector_deletes) == 1
    call = client.vector_deletes[0]
    assert call["vectors"] == ["meta_abstract_dense", "meta_abstract_bm25"]
    assert str(doc_id) in str(call["points"])


async def test_delete_vectors_noops_on_empty_names_or_missing_collection() -> None:
    present = _FakeDeleteClient()
    await QdrantIndexApi.delete_vectors(present, "col", [], uuid.uuid4())  # type: ignore[arg-type]
    assert present.vector_deletes == []

    absent = _FakeDeleteClient(exists=False)
    await QdrantIndexApi.delete_vectors(absent, "col", ["meta_x_dense"], uuid.uuid4())  # type: ignore[arg-type]
    assert absent.vector_deletes == []
