"""The single-branch rule — QdrantSearchApi.fuses is the one place deciding whether the hit scores are
a fusion or one vector's raw score — and the probe's raw_axis that the response score_kind reads."""

from shared_libs.services.db.qdrant import QdrantSearchApi, SparseVec


def test_fuses_only_with_more_than_one_branch() -> None:
    sparse = SparseVec(indices=[1], values=[1.0])
    assert not QdrantSearchApi.fuses({"content_dense": [0.1]}, None)
    assert not QdrantSearchApi.fuses(None, {"meta_x_bm25": sparse})
    assert QdrantSearchApi.fuses({"content_dense": [0.1]}, {"content_bm25": sparse})
    assert QdrantSearchApi.fuses({"content_dense": [0.1], "meta_x_dense": [0.2]}, None)


def test_probe_raw_axis(fastapi_app) -> None:
    from backend.libs.search import ScoreKindClassifier, SearchRetrievalProbe  # noqa: PLC0415

    # 1. No call → nothing to claim.
    assert SearchRetrievalProbe().raw_axis() is None
    # 2. One unfused dense call → raw dense.
    probe = SearchRetrievalProbe()
    probe.record_call("dense_only", False, ["a"], fused=False)
    assert ScoreKindClassifier.raw_kind(probe.raw_axis()) == "raw_dense"
    # 3. Any fused call, or calls on different axes, → fusion (None).
    probe.record_call("dense_only", False, ["a"], fused=True)
    assert probe.raw_axis() is None
    mixed = SearchRetrievalProbe()
    mixed.record_call("dense_only", False, [], fused=False)
    mixed.record_call("sparse_only", False, [], fused=False)
    assert mixed.raw_axis() is None
    # 4. A filter-only call (no vector) is never a raw score.
    none_call = SearchRetrievalProbe()
    none_call.record_call("none", True, [], fused=False)
    assert none_call.raw_axis() is None
