"""The cross-encoder rerank node: given a fake read port + a mocked /rerank HTTP call, it re-scores
the fused candidate pool by the returned index, stamps the cross-encoder provenance, and emits a
plain CandidateSet the hydrate node consumes unchanged. Also proves the fusion+rerank blob builds +
validates and that the rerank node re-orders a pool the fusion score ranked differently — all with
NO Qdrant, NO Postgres, NO network.
"""

import asyncio

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search import (
    COLLECTION_READ_CAPABILITY,
    CollectionReadPort,
    SearchPipeline,
)
from shared_libs.pipelines.search.nodes.rerank.cross_encoder.core import RerankCrossEncoderNode
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models.search import (
    Candidate,
    CandidateSet,
    Hit,
    QueryFilters,
    QuerySpec,
    RawQuery,
    SearchContract,
    SearchResult,
)


# ---------------------- Test doubles ---------------------- #
class _RerankFakeEmbedConfig(BaseEmbedConfig):
    """Config of the HTTP-free embedder the end-to-end rerank blob test rebuilds from the contract."""


@NodeRegistry.register("embed")
class _RerankFakeEmbedNode(BaseEmbedderNode):
    """A deterministic, HTTP-free embedder — a distinct kind from the other test's fake embedder."""

    KIND = "fake_rerank_embed"
    NAME = "Fake rerank-test embedder"
    SUMMARY = "Deterministic embedder for the rerank end-to-end test (no HTTP)."
    Config = _RerankFakeEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """A fixed 4-d dense vector per text — no network."""
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class _TextPort(CollectionReadPort):
    """A read port that hydrates each candidate id into a Hit carrying a passage text."""

    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts
        self.hydrated_ids: list[str] = []

    async def hybrid_search(self, encoded, filters, limit, targets=None, fusion="rrf"):
        """Unused by the rerank-node unit tests (the node reads only hydrate)."""
        raise AssertionError("hybrid_search must not be called by the rerank node")

    async def hydrate(self, chunk_ids):
        """Hydrate only the ids present in the fixture; an unknown id has no row (dropped)."""
        self.hydrated_ids = list(chunk_ids)
        return {
            chunk_id: Hit(
                chunk_id=chunk_id,
                document_id=f"doc-{chunk_id}",
                text=self._texts[chunk_id],
                metadata={},
            )
            for chunk_id in chunk_ids
            if chunk_id in self._texts
        }


def _install_fake_client(monkeypatch, scores_by_index: dict[int, float], seen: dict) -> None:
    """Patch the node's HTTP client so /rerank is a pure function of the passed texts (no network)."""

    async def _fake_rerank(self, query, texts, truncate):
        # Record what the node sent so the test can assert the (query, texts, truncate) contract.
        seen["query"] = query
        seen["texts"] = texts
        seen["truncate"] = truncate
        return [(index, scores_by_index[index]) for index in range(len(texts))]

    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.rerank.cross_encoder.core."
        "CrossEncoderRerankClient.rerank",
        _fake_rerank,
    )


def _run_node(node: RerankCrossEncoderNode, data) -> object:
    """Bind a port onto the node and run it once."""
    return asyncio.run(node.run(data))


# ---------------------- Node unit tests ---------------------- #
def test_rerank_re_scores_by_index_and_reorders(monkeypatch) -> None:
    """The node overwrites each candidate's score by the /rerank index and re-orders best-first."""
    # 1. A pool the FUSION score ranks a→b→c; the reranker will invert it to c→b→a.
    port = _TextPort({"a": "text a", "b": "text b", "c": "text c"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})

    seen: dict = {}
    _install_fake_client(monkeypatch, {0: 0.10, 1: 0.55, 2: 0.99}, seen)

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.9, source="hybrid"),
                Candidate(chunk_id="b", score=0.7, source="hybrid"),
                Candidate(chunk_id="c", score=0.5, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=3, candidate_k=3),
    )
    out = _run_node(node, data)

    # 2. The node sent the query text + the hydrated passages in fusion order, truncate on.
    assert seen == {"query": "q", "texts": ["text a", "text b", "text c"], "truncate": True}

    # 3. Scores are the cross-encoder [0, 1] values; the order is now inverted (c best).
    result = out.candidates.candidates
    assert [c.chunk_id for c in result] == ["c", "b", "a"]
    assert [c.score for c in result] == [0.99, 0.55, 0.10]
    assert {c.source for c in result} == {"cross_encoder"}

    # 4. The aggregate ScoredOutput score is the top-1 rerank score.
    assert out.score == 0.99


def test_rerank_caps_at_top_n_and_drops_the_tail(monkeypatch) -> None:
    """Only the top candidates by fusion score are hydrated, re-scored, and emitted — when the
    requested page (top_k) is within top_n, top_n is the effective cap and the tail is dropped."""
    port = _TextPort({"a": "ta", "b": "tb", "c": "tc"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config(top_n=2))
    node.bind({COLLECTION_READ_CAPABILITY: port})

    seen: dict = {}
    _install_fake_client(monkeypatch, {0: 0.3, 1: 0.8}, seen)

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.9, source="hybrid"),
                Candidate(chunk_id="b", score=0.7, source="hybrid"),
                Candidate(chunk_id="c", score=0.5, source="hybrid"),  # beyond top_n → dropped
            ]
        ),
        spec=QuerySpec(text="q", top_k=2, candidate_k=2),
    )
    out = _run_node(node, data)

    # 1. Only the two highest-fusion candidates were hydrated + judged (c never touched).
    assert port.hydrated_ids == ["a", "b"]
    assert seen["texts"] == ["ta", "tb"]

    # 2. The emitted pool is exactly the re-scored top_n, best-first — the tail is gone.
    assert [c.chunk_id for c in out.candidates.candidates] == ["b", "a"]
    assert [c.score for c in out.candidates.candidates] == [0.8, 0.3]


def test_rerank_judges_at_least_top_k_when_it_exceeds_top_n(monkeypatch) -> None:
    """When the requested page (top_k, from the API limit up to 100) exceeds config.top_n, the node
    must judge at least top_k candidates — otherwise a limit of 51-100 on a rerank-enabled collection
    silently returned <= top_n (default 50) hits. Here top_n=2 but top_k=3, so all three are judged."""
    port = _TextPort({"a": "ta", "b": "tb", "c": "tc"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config(top_n=2))
    node.bind({COLLECTION_READ_CAPABILITY: port})

    seen: dict = {}
    _install_fake_client(monkeypatch, {0: 0.3, 1: 0.8, 2: 0.6}, seen)

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.9, source="hybrid"),
                Candidate(chunk_id="b", score=0.7, source="hybrid"),
                Candidate(chunk_id="c", score=0.5, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=3, candidate_k=3),
    )
    out = _run_node(node, data)

    # All three were judged (top_k=3 > top_n=2), so the requested page is fully fillable.
    assert port.hydrated_ids == ["a", "b", "c"]
    assert seen["texts"] == ["ta", "tb", "tc"]
    # Re-ordered best-first by the cross-encoder score (b 0.8 > c 0.6 > a 0.3).
    assert [c.chunk_id for c in out.candidates.candidates] == ["b", "c", "a"]


def test_rerank_skips_vanished_rows_and_keeps_index_alignment(monkeypatch) -> None:
    """A candidate whose row vanished is dropped from BOTH texts and judged — index stays aligned."""
    # 1. The pool is a,b,c by fusion score, but 'b' has no row (deleted between search and rerank).
    port = _TextPort({"a": "text a", "c": "text c"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})

    # 2. Only two texts reach /rerank; index 0 → 'a', index 1 → 'c' (NOT 'b'). Score c above a.
    seen: dict = {}
    _install_fake_client(monkeypatch, {0: 0.20, 1: 0.90}, seen)

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.9, source="hybrid"),
                Candidate(chunk_id="b", score=0.7, source="hybrid"),  # vanished — no row
                Candidate(chunk_id="c", score=0.5, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=3, candidate_k=3),
    )
    out = _run_node(node, data)

    # 3. 'b' never reached the reranker; the two returned indices mapped to a and c, not shifted.
    assert seen["texts"] == ["text a", "text c"]
    result = out.candidates.candidates
    assert [c.chunk_id for c in result] == ["c", "a"]
    assert [c.score for c in result] == [0.90, 0.20]


def test_rerank_empty_pool_short_circuits(monkeypatch) -> None:
    """An empty candidate pool produces an empty result with a zero aggregate score (no HTTP)."""
    port = _TextPort({})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})

    def _boom(*_a, **_k):
        raise AssertionError("no /rerank call for an empty pool")

    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.rerank.cross_encoder.core."
        "CrossEncoderRerankClient.rerank",
        _boom,
    )

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(candidates=[]),
        spec=QuerySpec(text="q", top_k=3, candidate_k=3),
    )
    out = _run_node(node, data)
    assert out.candidates.candidates == []
    assert out.score == 0.0


# ---------------------- Degradation tests ---------------------- #
def _install_rerank_raiser(monkeypatch, exc: Exception) -> None:
    """Patch the node's HTTP client so /rerank always raises — a slow/cold or broken reranker."""

    async def _boom(self, query, texts, truncate):
        raise exc

    monkeypatch.setattr(
        "shared_libs.pipelines.search.nodes.rerank.cross_encoder.core."
        "CrossEncoderRerankClient.rerank",
        _boom,
    )


def test_rerank_degrades_to_fusion_order_on_timeout(monkeypatch) -> None:
    """A timed-out /rerank returns the fusion-order candidates un-reranked, with a degrade note."""
    port = _TextPort({"a": "text a", "b": "text b", "c": "text c"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})
    _install_rerank_raiser(monkeypatch, TimeoutError())

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.9, source="hybrid"),
                Candidate(chunk_id="b", score=0.7, source="hybrid"),
                Candidate(chunk_id="c", score=0.5, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=3, candidate_k=3),
    )
    out = _run_node(node, data)

    # 1. Same candidates, in the incoming fusion order — nothing re-scored or re-ordered.
    assert [c.chunk_id for c in out.candidates.candidates] == ["a", "b", "c"]
    assert [c.score for c in out.candidates.candidates] == [0.9, 0.7, 0.5]
    # 2. The degrade note is surfaced; the aggregate is the top fusion score (a sane ScoreBelow gate).
    assert out.candidates.degraded == "rerank skipped — reranker busy, fusion-order results"
    assert out.score == 0.9


def test_rerank_degrade_clamps_a_fusion_score_above_one(monkeypatch) -> None:
    """On degrade the aggregate is the incoming FUSION score, which is NOT on the cross-encoder scale
    and routinely exceeds 1.0 (RRF over 3+ prefetch branches → 1.5-2.0; DBSF > 1.0 with two). Since
    ScoredOutput.score is Field(le=1), an unclamped value would raise a ValidationError inside run()
    — turning the degrade path into a misleading 422 exactly when the reranker is down. It must clamp
    to 1.0 and still return the un-reranked candidates."""
    port = _TextPort({"a": "text a", "b": "text b"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})
    _install_rerank_raiser(monkeypatch, TimeoutError())

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=1.8, source="hybrid"),  # RRF over 3+ branches
                Candidate(chunk_id="b", score=1.2, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=2, candidate_k=2),
    )
    out = _run_node(node, data)  # must NOT raise a ValidationError

    # The candidates ride through un-reranked (raw fusion scores preserved on each candidate)...
    assert [c.chunk_id for c in out.candidates.candidates] == ["a", "b"]
    assert [c.score for c in out.candidates.candidates] == [1.8, 1.2]
    # ...but the NODE-LEVEL aggregate score is clamped into the [0, 1] ScoredOutput range.
    assert out.score == 1.0
    assert out.candidates.degraded


def test_rerank_degrades_to_fusion_order_on_provider_error(monkeypatch) -> None:
    """A generic provider error degrades the same way — fusion-order fallback, never a raise."""
    port = _TextPort({"a": "text a", "b": "text b"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})
    _install_rerank_raiser(monkeypatch, RuntimeError("connection refused"))

    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[
                Candidate(chunk_id="a", score=0.8, source="hybrid"),
                Candidate(chunk_id="b", score=0.4, source="hybrid"),
            ]
        ),
        spec=QuerySpec(text="q", top_k=2, candidate_k=2),
    )
    out = _run_node(node, data)

    assert [c.chunk_id for c in out.candidates.candidates] == ["a", "b"]
    assert out.candidates.degraded == "rerank skipped — reranker busy, fusion-order results"
    assert out.score == 0.8


def test_rerank_degrade_preserves_incoming_note(monkeypatch) -> None:
    """When the pool already carries an encode-degrade note, the rerank note is joined onto it."""
    port = _TextPort({"a": "text a"})
    node = RerankCrossEncoderNode(id="rerank", config=RerankCrossEncoderNode.Config())
    node.bind({COLLECTION_READ_CAPABILITY: port})
    _install_rerank_raiser(monkeypatch, TimeoutError())

    incoming = "semantic unavailable — embedder busy, lexical-only results"
    data = RerankCrossEncoderNode.Consumes(
        candidates=CandidateSet(
            candidates=[Candidate(chunk_id="a", score=0.6, source="hybrid")],
            degraded=incoming,
        ),
        spec=QuerySpec(text="q", top_k=1, candidate_k=1),
    )
    out = _run_node(node, data)

    # Both the incoming encode note and the rerank note are present, joined with "; ".
    assert (
        out.candidates.degraded
        == f"{incoming}; rerank skipped — reranker busy, fusion-order results"
    )
    assert [c.chunk_id for c in out.candidates.candidates] == ["a"]


# ---------------------- Blob wiring tests ---------------------- #
def test_rerank_blob_builds_and_validates_clean() -> None:
    """The fusion+rerank blob builds and passes the graph validator with ZERO issues."""
    blob = SearchPipeline.rerank_blob()
    assert [node.id for node in blob.nodes] == [
        "normalize",
        "encode",
        "retrieve",
        "rerank",
        "hydrate",
        "deliver",
    ]
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []


def test_rerank_blob_hydrate_binds_to_rerank_not_retrieve() -> None:
    """hydrate consumes the rerank node's re-scored CandidateSet — the wiring the design requires."""
    binding = SearchPipeline.rerank_blob().bindings["hydrate"]["candidates"]
    assert binding.node_id == "rerank"
    assert binding.field_name == "candidates"


class _EndToEndPort(CollectionReadPort):
    """A port whose fusion pool the reranker will re-order, proving rerank changes the final result."""

    async def hybrid_search(self, encoded, filters, limit, targets=None, fusion="rrf"):
        """Fusion ranks a>b>c; the mocked reranker below inverts it to c>b>a."""
        return [
            Candidate(chunk_id="a", score=0.9, source="hybrid"),
            Candidate(chunk_id="b", score=0.7, source="hybrid"),
            Candidate(chunk_id="c", score=0.5, source="hybrid"),
        ]

    async def hydrate(self, chunk_ids):
        """Hydrate any requested id into a Hit."""
        return {
            chunk_id: Hit(
                chunk_id=chunk_id, document_id=f"doc-{chunk_id}", text=chunk_id, metadata={}
            )
            for chunk_id in chunk_ids
        }


def test_rerank_blob_runs_end_to_end_and_changes_order(monkeypatch) -> None:
    """The whole fusion+rerank graph runs to a SearchResult whose order the reranker inverted."""
    seen: dict = {}
    _install_fake_client(monkeypatch, {0: 0.10, 1: 0.55, 2: 0.99}, seen)

    group = PipelineBuilder().build(SearchPipeline.rerank_blob())
    port = _EndToEndPort()
    for child in group.children:
        if isinstance(child, ActionNode):
            child.bind({COLLECTION_READ_CAPABILITY: port})

    run_input = {
        "query": RawQuery(text="hello", top_k=3, flags={}),
        "filters": QueryFilters(filters={}),
        "contract": SearchContract(
            collection_id="col-1",
            embed_kind="fake_rerank_embed",
            embed_config={"model": "fake", "embed_sparse": False},
        ),
    }
    output, record = asyncio.run(FlowEngine().execute(group, run_input))

    assert record.status.value == "success", record
    result: SearchResult = output.result
    # Fusion order was a,b,c; the cross-encoder inverted it — the delivered order proves rerank ran.
    assert [hit.chunk_id for hit in result.hits] == ["c", "b", "a"]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert [hit.score for hit in result.hits] == [0.99, 0.55, 0.10]


def test_other_rerank_kinds_stay_placeholders() -> None:
    """The llm rerank remains a hidden placeholder — only cross_encoder is selectable."""
    assert NodeRegistry.get("rerank", "llm").describe().selectable is False
    assert NodeRegistry.get("rerank", "cross_encoder").describe().selectable is True
