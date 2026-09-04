"""QdrantIndexApi write batching: every whole-document write path splits into byte-bounded batches so
no single request crosses Qdrant's ~32 MB body limit. upsert already did; update_vectors (the post-hoc
meta-vector sync) previously sent ALL points in one request and 400'd on a large document, silently
breaking the sync; set_payload chunks its per-point operations by count. A fake client records the
batches — no Qdrant."""

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
