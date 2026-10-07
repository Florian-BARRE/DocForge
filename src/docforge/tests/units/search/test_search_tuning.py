"""Per-request search tuning (C3): the pure nodes honour the request flags (rerank skip → the reranker
is never called; fusion override reaches the read port), the rerank node keeps the fusion score, the
hydrate node records score provenance, SearchTuning builds the flags / checks the blob / relabels
score_kind, and the finalize step applies min_score BEFORE the per-document cap. No store, no network.
"""

import asyncio

import pytest

from backend.libs.search import SearchResultFinalizer, SearchTuning, SearchTuningError
from shared_libs.pipelines.search import (
    COLLECTION_READ_CAPABILITY,
    CollectionReadPort,
    SearchPipeline,
)
from shared_libs.pipelines.search.nodes.postprocess.hydrate.core import PostprocessHydrateNode
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.core import RerankCrossEncoderNode
from shared_libs.pipelines.search.nodes.retrieve.hybrid.core import RetrieveHybridNode
from shared_libs.public_models.search import (
    FUSION_FLAG,
    RERANK_FLAG,
    Candidate,
    CandidateSet,
    EncodedQuery,
    Hit,
    QuerySpec,
    SearchResult,
)


class _Port(CollectionReadPort):
    """A read port recording the fusion it was asked for and hydrating every id."""

    def __init__(self) -> None:
        self.fusion: str | None = None

    async def hybrid_search(
        self, encoded, filters, limit, targets=None, fusion="rrf", measure_branch_contribution=False
    ):
        """Record the fusion strategy and return one candidate."""
        self.fusion = fusion
        return [Candidate(chunk_id="a", score=0.5, source="hybrid")]

    async def hydrate(self, chunk_ids):
        """Every id hydrates to a hit of document doc-<id>."""
        return {cid: Hit(chunk_id=cid, document_id=f"doc-{cid}", text=cid) for cid in chunk_ids}


def _pool() -> CandidateSet:
    """A fused pool ranked a → b."""
    return CandidateSet(
        candidates=[
            Candidate(chunk_id="a", score=1.4, source="hybrid"),
            Candidate(chunk_id="b", score=0.7, source="hybrid"),
        ]
    )


# ---------------------------------------------------------------- rerank node


def test_rerank_flag_false_skips_without_calling_the_reranker(monkeypatch) -> None:
    """flags[rerank]=False → the pool passes through untouched; the provider is never called."""

    async def _boom(self, *args, **kwargs):
        raise AssertionError("the reranker must not be called when the request skips it")

    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.rerank.cross_encoder.core."
        "CrossEncoderRerankClient.rerank",
        _boom,
    )
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: _Port()})
    pool = _pool()
    data = RerankCrossEncoderNode.Consumes(
        candidates=pool,
        spec=QuerySpec(text="q", top_k=2, candidate_k=2, flags={RERANK_FLAG: False}),
    )
    out = asyncio.run(node.run(data))

    assert out.candidates == pool
    assert out.score == 1.0  # a caller-requested skip is "not judged" (never escalation bait)


def test_rerank_keeps_the_fusion_score(monkeypatch) -> None:
    """A re-scored candidate carries its incoming fusion score alongside the rerank score."""

    async def _scores(self, query, texts, truncate):
        return [(0, 0.2), (1, 0.9)]

    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.rerank.cross_encoder.core."
        "CrossEncoderRerankClient.rerank",
        _scores,
    )
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: _Port()})
    data = RerankCrossEncoderNode.Consumes(
        candidates=_pool(), spec=QuerySpec(text="q", top_k=2, candidate_k=2)
    )
    out = asyncio.run(node.run(data))

    by_id = {c.chunk_id: c for c in out.candidates.candidates}
    assert (by_id["b"].score, by_id["b"].fusion_score) == (0.9, 0.7)
    assert (by_id["a"].score, by_id["a"].fusion_score) == (0.2, 1.4)


# ---------------------------------------------------------------- retrieve node


@pytest.mark.parametrize(
    ("flags", "expected"),
    [({}, "rrf"), ({FUSION_FLAG: "dbsf"}, "dbsf"), ({FUSION_FLAG: "x"}, "rrf")],
)
def test_retrieve_fusion_override_reaches_the_port(flags, expected) -> None:
    """flags[fusion] overrides the configured fusion; an unknown value keeps the configured one."""
    port = _Port()
    node = RetrieveHybridNode(id="retrieve", config=RetrieveHybridNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})
    data = RetrieveHybridNode.Consumes(
        spec=QuerySpec(text="q", top_k=1, candidate_k=1, flags=flags),
        encoded=EncodedQuery(dense=[0.1]),
    )
    asyncio.run(node.run(data))
    assert port.fusion == expected


# ---------------------------------------------------------------- hydrate node


def test_hydrate_records_score_provenance() -> None:
    """A reranked candidate → fusion_score + rerank_score; an un-reranked one → fusion_score only."""
    node = PostprocessHydrateNode(id="hydrate", config=PostprocessHydrateNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: _Port()})
    data = PostprocessHydrateNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="r", score=0.9, source="cross_encoder", fusion_score=0.03),
                Candidate(chunk_id="f", score=0.02, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=2, candidate_k=2),
    )
    hits = asyncio.run(node.run(data)).ranked.hits
    assert (hits[0].fusion_score, hits[0].rerank_score) == (0.03, 0.9)
    assert (hits[1].fusion_score, hits[1].rerank_score) == (0.02, None)


# ---------------------------------------------------------------- SearchTuning (app-side)


def test_tuning_flags_and_blob_check() -> None:
    """Only deviations become flags; rerank=True on a rerank-less blob is a typed error."""
    assert SearchTuning().flags() == {}
    assert SearchTuning(rerank=True).flags() == {}
    assert SearchTuning(rerank=False, fusion="dbsf").flags() == {
        RERANK_FLAG: False,
        FUSION_FLAG: "dbsf",
    }

    default_blob = SearchPipeline.default_blob().model_dump(mode="json")
    rerank_blob = SearchPipeline.rerank_blob().model_dump(mode="json")
    SearchTuning(rerank=True).check_blob(rerank_blob)
    SearchTuning(rerank=False).check_blob(default_blob)
    with pytest.raises(SearchTuningError, match="no rerank stage"):
        SearchTuning(rerank=True).check_blob(default_blob)


def test_tuning_score_kind() -> None:
    """A skipped rerank reports the fusion kind; a fusion override names the strategy that ran."""
    rerank, rrf = "cross_encoder_rerank", "rrf_fusion"
    assert SearchTuning().score_kind(rerank, rrf) == rerank
    assert SearchTuning(rerank=False).score_kind(rerank, rrf) == rrf
    assert SearchTuning(rerank=False, fusion="dbsf").score_kind(rerank, rrf) == "dbsf_fusion"
    assert SearchTuning(fusion="dbsf").score_kind(rerank, rrf) == rerank
    assert SearchTuning(fusion="dbsf").score_kind(rrf, rrf) == "dbsf_fusion"


# ---------------------------------------------------------------- finalize: min_score → group_by


def _result() -> SearchResult:
    """Four ranked hits over two documents, scores 0.9 / 0.8 / 0.4 / 0.3."""
    hits = [
        Hit(chunk_id="1", document_id="A", score=0.9, rank=1),
        Hit(chunk_id="2", document_id="A", score=0.8, rank=2),
        Hit(chunk_id="3", document_id="B", score=0.4, rank=3),
        Hit(chunk_id="4", document_id="B", score=0.3, rank=4),
    ]
    return SearchResult(query="q", hits=hits, debug={"hit_count": 4})


def test_finalizer_none_when_untuned() -> None:
    """No min_score and no grouping → no finalize step (the default path is untouched)."""
    assert SearchResultFinalizer.build(10, None, None) is None


def test_min_score_drops_the_tail() -> None:
    """Hits below the threshold are dropped (inclusive bound); the debug bag says how many."""
    out = SearchResultFinalizer.build(10, None, 0.4)(_result())
    assert [hit.chunk_id for hit in out.hits] == ["1", "2", "3"]
    assert out.debug["hit_count"] == 3
    assert out.debug["min_score"]["threshold"] == 0.4
    assert out.debug["min_score"]["dropped"] == 1
    assert out.debug["min_score"]["top_dropped_score"] is not None


def test_min_score_applies_before_grouping() -> None:
    """min_score cuts first, then the per-document cap runs over the survivors."""
    out = SearchResultFinalizer.build(10, 1, 0.5)(_result())
    # B's hits are all below 0.5 → only A's best survives the cap (not B's 0.4 filling the page).
    assert [hit.chunk_id for hit in out.hits] == ["1"]
    assert out.debug["min_score"]["dropped"] == 2
    assert out.debug["grouping"]["fetched"] == 2


def test_min_score_hint_when_threshold_empties_the_answer() -> None:
    """The threshold, not the filters, emptied the answer — the hint says so with the best score."""
    from backend.libs.search import MinScoreHint  # noqa: PLC0415

    (hint,) = MinScoreHint.build({"threshold": 0.5, "dropped": 4, "top_dropped_score": 0.031}, 0)
    assert hint.field == "min_score"
    assert "4 hit(s)" in hint.message and "0.0310" in hint.message


def test_min_score_hint_silent_when_hits_remain_or_no_threshold() -> None:
    from backend.libs.search import MinScoreHint  # noqa: PLC0415

    assert MinScoreHint.build({"threshold": 0.5, "dropped": 2, "top_dropped_score": 0.4}, 3) == []
    assert MinScoreHint.build({}, 0) == []


def test_rerank_skip_with_low_fusion_scores_does_not_look_low_quality() -> None:
    """A skipped rerank over RRF-scale scores (~0.03) still reports 1.0 — a ScoreBelow edge tuned for
    cross-encoder scores must not fire just because the caller asked to skip reranking."""
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: _Port()})
    pool = CandidateSet(candidates=[Candidate(chunk_id="a", score=0.032, source="hybrid")])
    data = RerankCrossEncoderNode.Consumes(
        candidates=pool,
        spec=QuerySpec(text="q", top_k=1, candidate_k=1, flags={RERANK_FLAG: False}),
    )
    out = asyncio.run(node.run(data))
    assert out.score == 1.0
    assert out.candidates.candidates[0].score == 0.032  # candidates keep their own fusion scores
