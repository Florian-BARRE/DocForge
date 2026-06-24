# ====== Code Summary ======
# Unit tests for QdrantSearchHelpers against a fake AsyncQdrantClient (no live Qdrant).
# Covers: candidate sizing + score_threshold passthrough to query_points, per-vector
# ranked lists (ids + scores), RRF vs DBSF fusion selection, payload hydration shape,
# and dense-vector fetch for MMR.

import types

import pytest

from common_libs.search.field_index import RetrievalTuning
from common_libs.storage.qdrant.search import QdrantSearchHelpers


# ── Fake Qdrant client ──────────────────────────────────────────────────────────


def _point(pid, score):
    return types.SimpleNamespace(id=pid, score=score)


def _record(pid, payload=None, vector=None):
    return types.SimpleNamespace(id=pid, payload=payload or {}, vector=vector)


class FakeQdrant:
    """
    Minimal AsyncQdrantClient stand-in that records query_points calls and returns
    canned per-vector hits. ``points_by_vector`` maps a named vector to a list of
    ``(id, score)`` tuples returned best-first.
    """

    def __init__(self, points_by_vector, vectors_by_id=None):
        self._points = points_by_vector
        self._vectors = vectors_by_id or {}
        self.calls = []  # recorded query_points kwargs

    async def query_points(self, **kwargs):
        self.calls.append(kwargs)
        vname = kwargs["using"]
        pts = [_point(pid, sc) for pid, sc in self._points.get(vname, [])]
        return types.SimpleNamespace(points=pts[: kwargs["limit"]])

    async def retrieve(self, *, collection_name, ids, with_payload=False, with_vectors=False):
        out = []
        for pid in ids:
            vec = None
            if with_vectors:
                v = self._vectors.get(pid)
                # named-vector retrieve returns a dict {vector_name: vector}
                if v is not None:
                    vec = {with_vectors[0]: v} if isinstance(with_vectors, list) else v
            out.append(_record(pid, payload={"pages": [1]}, vector=vec))
        return out


# ── run_multi_search ──────────────────────────────────────────────────────────


class TestRunMultiSearch:
    @pytest.mark.asyncio
    async def test_candidate_limit_and_threshold_passed_to_query_points(self) -> None:
        client = FakeQdrant({"content_dense": [("a", 0.9)], "content_bm25": [("a", 2.0)]})
        tuning = RetrievalTuning(candidate_multiplier=3, min_candidates=20, score_threshold=0.25)
        await QdrantSearchHelpers.run_multi_search(
            client=client, collection_name="c",
            dense_query=[0.1], sparse_query={1: 1.0},
            dense_vectors=["content_dense"], sparse_vectors=["content_bm25"],
            weights={"content_dense": 1.0, "content_bm25": 1.0},
            top_k=10, payload_filter=None, tuning=tuning,
        )
        # candidate_limit = max(10*3, 20) = 30 ; score_threshold forwarded
        assert all(c["limit"] == 30 for c in client.calls)
        assert all(c["score_threshold"] == 0.25 for c in client.calls)
        assert all(c["with_payload"] is False for c in client.calls)

    @pytest.mark.asyncio
    async def test_min_candidates_floor(self) -> None:
        client = FakeQdrant({"content_dense": [("a", 0.9)]})
        tuning = RetrievalTuning(candidate_multiplier=3, min_candidates=20)
        await QdrantSearchHelpers.run_multi_search(
            client=client, collection_name="c", dense_query=[0.1], sparse_query=None,
            dense_vectors=["content_dense"], sparse_vectors=[], weights={"content_dense": 1.0},
            top_k=1, payload_filter=None, tuning=tuning,
        )
        assert client.calls[0]["limit"] == 20  # max(1*3, 20)

    @pytest.mark.asyncio
    async def test_sparse_skipped_when_no_sparse_query(self) -> None:
        client = FakeQdrant({"content_dense": [("a", 0.9)], "content_bm25": [("a", 2.0)]})
        await QdrantSearchHelpers.run_multi_search(
            client=client, collection_name="c", dense_query=[0.1], sparse_query=None,
            dense_vectors=["content_dense"], sparse_vectors=["content_bm25"],
            weights={"content_dense": 1.0, "content_bm25": 1.0},
            top_k=5, payload_filter=None, tuning=RetrievalTuning(),
        )
        # Only the dense vector is queried — no sparse query vector available.
        assert [c["using"] for c in client.calls] == ["content_dense"]

    @pytest.mark.asyncio
    async def test_rrf_fusion_orders_by_agreement(self) -> None:
        # 'a' ranks high in both vectors → should win under RRF.
        client = FakeQdrant({
            "content_dense": [("b", 0.9), ("a", 0.8)],
            "content_bm25": [("a", 5.0), ("c", 1.0)],
        })
        out = await QdrantSearchHelpers.run_multi_search(
            client=client, collection_name="c", dense_query=[0.1], sparse_query={1: 1.0},
            dense_vectors=["content_dense"], sparse_vectors=["content_bm25"],
            weights={"content_dense": 1.0, "content_bm25": 1.0},
            top_k=5, payload_filter=None, tuning=RetrievalTuning(fusion="rrf"),
        )
        fused_ids = [cid for cid, _ in out["fused"]]
        assert fused_ids[0] == "a"
        # ranked is ids-only for the debug per-vector breakdown
        assert out["ranked"]["content_dense"] == ["b", "a"]
        # results are hydrated dicts with id/score/payload
        assert out["results"][0]["id"] == "a"
        assert "payload" in out["results"][0]

    @pytest.mark.asyncio
    async def test_dbsf_fusion_selected(self) -> None:
        client = FakeQdrant({
            "content_dense": [("a", 0.9), ("b", 0.1)],
            "content_bm25": [("b", 9.0), ("a", 1.0)],
        })
        out = await QdrantSearchHelpers.run_multi_search(
            client=client, collection_name="c", dense_query=[0.1], sparse_query={1: 1.0},
            dense_vectors=["content_dense"], sparse_vectors=["content_bm25"],
            weights={"content_dense": 1.0, "content_bm25": 1.0},
            top_k=5, payload_filter=None, tuning=RetrievalTuning(fusion="dbsf"),
        )
        # DBSF normalizes raw scores then sums — both candidates present, ordered by fused score.
        assert {cid for cid, _ in out["fused"]} == {"a", "b"}


# ── fetch_vectors ────────────────────────────────────────────────────────────


class TestFetchVectors:
    @pytest.mark.asyncio
    async def test_returns_present_vectors_only(self) -> None:
        client = FakeQdrant({}, vectors_by_id={"a": [0.1, 0.2], "b": None})
        out = await QdrantSearchHelpers.fetch_vectors(
            client=client, collection_name="c", ids=["a", "b", "missing"],
            vector_name="content_dense",
        )
        assert out == {"a": [0.1, 0.2]}  # b has no vector, missing absent

    @pytest.mark.asyncio
    async def test_empty_ids(self) -> None:
        client = FakeQdrant({})
        assert await QdrantSearchHelpers.fetch_vectors(
            client=client, collection_name="c", ids=[], vector_name="content_dense"
        ) == {}
