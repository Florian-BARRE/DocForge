"""The search pipeline: the default graph builds + validates clean, and executes end-to-end to a
ranked SearchResult with a MOCKED CollectionReadPort (no Qdrant, no Postgres) and a fake, HTTP-free
embedder — proving the graph is real, not scaffolding.

Wave 1 (pipeline agent): artefacts + families + must-have nodes + facade + port interface. The
engine/builder/validator are reused verbatim; the read port is bound by hand here exactly as Wave 2's
request-context resolver will bind it before FlowEngine.execute.
"""

import asyncio

import pytest

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search import (
    COLLECTION_READ_CAPABILITY,
    CollectionReadPort,
    SearchPipeline,
)
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models.search import (
    Candidate,
    EncodedQuery,
    Hit,
    QueryFilters,
    RawQuery,
    SearchContract,
    SearchResult,
    SearchTarget,
    default_content_targets,
)


# ---------------------- Test doubles ---------------------- #
class _FakeEmbedConfig(BaseEmbedConfig):
    """Config of the HTTP-free test embedder."""


@NodeRegistry.register("embed")
class FakeEmbedNode(BaseEmbedderNode):
    """A deterministic, HTTP-free embedder the encode node rebuilds from the contract."""

    # 'fake_' prefix: the design-surface test skips it, and it never enters a real palette.
    KIND = "fake_embed"
    NAME = "Fake embedder"
    SUMMARY = "Deterministic embedder for tests (no HTTP)."
    Config = _FakeEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """A fixed 4-d dense vector per text — no network."""
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class MockCollectionReadPort(CollectionReadPort):
    """A read port that returns 3 fake candidates and hydrates them — no store."""

    def __init__(self) -> None:
        self.hybrid_calls: list[tuple[dict, int]] = []
        self.hydrated_ids: list[str] = []

    async def hybrid_search(self, encoded, filters, limit, targets=None, rescore_pool_size=None):
        """Return 3 fake candidates, best-first (records the call for assertions)."""
        assert isinstance(encoded, EncodedQuery)
        self.hybrid_calls.append((filters, limit))
        return [
            Candidate(chunk_id="c1", score=0.9, source="hybrid"),
            Candidate(chunk_id="c2", score=0.7, source="hybrid"),
            Candidate(chunk_id="c3", score=0.5, source="hybrid"),
        ]

    async def hydrate(self, chunk_ids):
        """Hydrate each id into a Hit carrying document_id/text/metadata."""
        self.hydrated_ids = list(chunk_ids)
        return {
            chunk_id: Hit(
                chunk_id=chunk_id,
                document_id=f"doc-{chunk_id}",
                text=f"text of {chunk_id}",
                metadata={"k": chunk_id},
            )
            for chunk_id in chunk_ids
        }


def _fake_run_input() -> dict:
    """The minimal search run-input: a raw query, empty filters, a fake-embedder contract."""
    return {
        "query": RawQuery(text="  Hello World  ", top_k=3, flags={}),
        "filters": QueryFilters(filters={}),
        "contract": SearchContract(
            collection_id="col-1",
            embed_kind="fake_embed",
            embed_config={"model": "fake", "embed_sparse": False},
        ),
    }


def _bind_read_port(group, port: CollectionReadPort) -> None:
    """Inject the read port into every port-backed node (what Wave 2's resolver does)."""
    for child in group.children:
        if isinstance(child, ActionNode):
            child.bind({COLLECTION_READ_CAPABILITY: port})


# ---------------------- Tests ---------------------- #
def test_search_default_blob_builds_and_validates_clean() -> None:
    """The default search graph builds and validates with ZERO structural issues."""
    blob = SearchPipeline.default_blob()
    ids = [node.id for node in blob.nodes]
    assert ids == ["normalize", "encode", "retrieve", "hydrate", "deliver"]

    group = PipelineBuilder().build(blob)
    issues = GraphValidator().validate(group)
    assert issues == [], issues


def test_search_graph_executes_end_to_end_to_a_ranked_result() -> None:
    """With a mocked port + fake embedder, the graph runs to a SearchResult of 3 ranked hits."""
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    port = MockCollectionReadPort()
    _bind_read_port(group, port)

    output, record = asyncio.run(FlowEngine().execute(group, _fake_run_input()))

    # 1. The run succeeded and produced the terminal contract.
    assert record.status.value == "success", record
    result: SearchResult = output.result
    assert isinstance(result, SearchResult)

    # 2. Three hits, ranked best-first, hydrated, labelled by the original query.
    assert result.query == "  Hello World  "  # the ORIGINAL text, not the normalised form
    assert [hit.chunk_id for hit in result.hits] == ["c1", "c2", "c3"]
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert [hit.document_id for hit in result.hits] == ["doc-c1", "doc-c2", "doc-c3"]
    assert result.hits[0].score == 0.9
    assert result.debug == {"hit_count": 3}

    # 3. The retrieve node drove the port with the over-sampled candidate_k (max(3*4, 100) = 100).
    assert port.hybrid_calls == [({}, 100)]
    assert port.hydrated_ids == ["c1", "c2", "c3"]


class CuttingReadPort(CollectionReadPort):
    """A port whose retrieval pool is larger than top_k and out of score order — proves the cut."""

    def __init__(self) -> None:
        self.hydrated_ids: list[str] = []

    async def hybrid_search(self, encoded, filters, limit, targets=None, rescore_pool_size=None):
        """Return 5 candidates in NON-descending order so ranking-before-cut is observable."""
        return [
            Candidate(chunk_id="lo", score=0.1, source="hybrid"),
            Candidate(chunk_id="top", score=0.9, source="hybrid"),
            Candidate(chunk_id="mid", score=0.5, source="hybrid"),
            Candidate(chunk_id="hi", score=0.7, source="hybrid"),
            Candidate(chunk_id="bot", score=0.2, source="hybrid"),
        ]

    async def hydrate(self, chunk_ids):
        """Record exactly which ids were hydrated (the cut set) and shape them into Hits."""
        self.hydrated_ids = list(chunk_ids)
        return {
            chunk_id: Hit(
                chunk_id=chunk_id, document_id=f"doc-{chunk_id}", text=chunk_id, metadata={}
            )
            for chunk_id in chunk_ids
        }


def test_hydrate_node_cuts_to_top_k_and_hydrates_only_the_cut_set() -> None:
    """The pool is ranked then cut to top_k; ONLY the cut set is hydrated (no wholesale hydration)."""
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    port = CuttingReadPort()
    _bind_read_port(group, port)

    run_input = _fake_run_input()
    run_input["query"] = RawQuery(text="hello", top_k=2, flags={})

    output, record = asyncio.run(FlowEngine().execute(group, run_input))

    # 1. Only the 2 highest-scored candidates were hydrated, in descending score order.
    assert record.status.value == "success", record
    assert port.hydrated_ids == ["top", "hi"]

    # 2. The delivered result carries exactly those 2, ranked 1..2 (not the full pool of 5).
    result: SearchResult = output.result
    assert [hit.chunk_id for hit in result.hits] == ["top", "hi"]
    assert [hit.rank for hit in result.hits] == [1, 2]
    assert [hit.score for hit in result.hits] == [0.9, 0.7]


def test_query_normalize_preserves_case_by_default_and_folds_only_when_asked() -> None:
    """Default keeps the query's case (aligned with original-case documents); fold_case=True lowers it.

    Documents are embedded from their original-case text, so BGE-M3 tokenizes them mixed-case on both
    the dense and sparse axes. Lower-casing only the query would misalign query and document vectors
    and cost recall — so the default must preserve case. The knob still folds when explicitly set.
    """
    from shared_libs.pipelines.search.nodes.query.normalize.core import (
        QueryNormalizeConfig,
        QueryNormalizeConsumes,
        QueryNormalizeNode,
    )

    raw = RawQuery(text="  AES-256 Encryption Policy  ", top_k=5, flags={})
    filters = QueryFilters(filters={})

    default_node = QueryNormalizeNode(id="n", config=QueryNormalizeConfig())
    default_out = asyncio.run(default_node.run(QueryNormalizeConsumes(query=raw, filters=filters)))
    assert default_out.spec.text == "AES-256 Encryption Policy"  # trimmed, case preserved

    folding_node = QueryNormalizeNode(id="n", config=QueryNormalizeConfig(fold_case=True))
    folding_out = asyncio.run(folding_node.run(QueryNormalizeConsumes(query=raw, filters=filters)))
    assert folding_out.spec.text == "aes-256 encryption policy"  # opt-in still works


def test_search_palette_lists_the_registered_families() -> None:
    """The palette exposes every search family with described nodes (must-have kinds present)."""
    palette = SearchPipeline.palette()
    by_family = {family.family: {node.kind for node in family.nodes} for family in palette.families}
    assert "normalize" in by_family["query"]
    assert "collection" in by_family["encode"]
    assert "hybrid" in by_family["retrieve"]
    assert "hydrate" in by_family["postprocess"]
    assert "hits" in by_family["deliver"]
    # Every family carries UI metadata (title + description), like the ingest palette.
    assert all(family.title and family.description for family in palette.families)


def test_deliver_family_is_scoped_per_pipeline_kind() -> None:
    """The SHARED ``deliver`` family shows only each pipeline kind's own terminal — no leak.

    ``deliver`` is registered by both pipelines (search's ``hits``, ingestion's ``bundle``). Each
    palette must scope the family to its own kind: the search palette must NOT list ``bundle`` and
    the ingest palette must NOT list ``hits``. Scoped in both the default and the full palette.
    """
    for full in (False, True):
        search_deliver = _deliver_kinds(SearchPipeline.palette(full=full))
        ingest_deliver = _deliver_kinds(IngestPipeline.palette(full=full))
        assert search_deliver == {"hits"}, (full, search_deliver)
        assert ingest_deliver == {"bundle"}, (full, ingest_deliver)


def _deliver_kinds(palette) -> set[str]:
    """Extract the set of kinds the palette lists under the ``deliver`` family."""
    deliver = next(family for family in palette.families if family.family == "deliver")
    return {node.kind for node in deliver.nodes}


def test_search_placeholders_are_registered_but_hidden() -> None:
    """The future methods are registered (discoverable) yet SELECTABLE=False (out of the palette)."""
    hidden = {
        "query": {"understand", "rewrite", "multi", "hyde"},
        "retrieve": {"dense", "sparse"},
        "fuse": {"rrf", "weighted"},
        "rerank": {"colbert", "llm"},
        "postprocess": {"dedup_document", "mmr", "parent_expand", "assemble"},
    }
    palette = {f.family: {n.kind for n in f.nodes} for f in SearchPipeline.palette().families}
    for family, kinds in hidden.items():
        # 1. Hidden from the palette's method picker.
        assert palette[family].isdisjoint(kinds), (family, palette[family] & kinds)
        # 2. Still registered + describable, and rerank placeholders advertise scored=True.
        for kind in kinds:
            described = NodeRegistry.get(family, kind).describe()
            assert described.selectable is False
    assert NodeRegistry.get("rerank", "colbert").describe().scored is True


class TargetCapturingReadPort(CollectionReadPort):
    """A read port that records the exact `targets` it was driven with — no store."""

    def __init__(self) -> None:
        self.targets_seen: list = None

    async def hybrid_search(self, encoded, filters, limit, targets=None, rescore_pool_size=None):
        self.targets_seen = targets
        return [Candidate(chunk_id="c1", score=0.9, source="hybrid")]

    async def hydrate(self, chunk_ids):
        return {
            chunk_id: Hit(chunk_id=chunk_id, document_id="doc", text="t", metadata={})
            for chunk_id in chunk_ids
        }


def test_search_targets_carry_through_to_the_read_port() -> None:
    """A caller-selected metadata search target reaches the port's hybrid_search UNCHANGED."""
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    port = TargetCapturingReadPort()
    _bind_read_port(group, port)

    targets = [SearchTarget(field="tags", semantic=True)]
    run_input = _fake_run_input()
    run_input["query"] = RawQuery(text="hello", top_k=3, search_targets=targets, flags={})

    output, record = asyncio.run(FlowEngine().execute(group, run_input))

    assert record.status.value == "success", record
    assert port.targets_seen == targets


def test_empty_search_targets_falls_back_to_default_content_targets() -> None:
    """An EMPTY search_targets list normalises back to the content default (never zero targets)."""
    group = PipelineBuilder().build(SearchPipeline.default_blob())
    port = TargetCapturingReadPort()
    _bind_read_port(group, port)

    run_input = _fake_run_input()
    run_input["query"] = RawQuery(text="hello", top_k=3, search_targets=[], flags={})

    output, record = asyncio.run(FlowEngine().execute(group, run_input))

    assert record.status.value == "success", record
    assert port.targets_seen == default_content_targets()


@pytest.mark.parametrize("kind", ["understand", "colbert", "rrf", "mmr"])
def test_placeholder_bodies_raise(kind: str) -> None:
    """A placeholder never runs — its body raises NotImplementedError if ever invoked."""
    family = {"understand": "query", "colbert": "rerank", "rrf": "fuse", "mmr": "postprocess"}[kind]
    node_class = NodeRegistry.get(family, kind)
    node = node_class(id="x", config=node_class.Config())
    with pytest.raises(NotImplementedError):
        # The body raises before it ever reads its input — no valid Consumes needed.
        asyncio.run(node.run(None))
