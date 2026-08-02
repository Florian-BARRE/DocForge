"""Embed stage: batching, dense+sparse, semantic field vectors, chunk linkage, and the trace's
record strip (large numeric vectors compacted to a placeholder — never the raw payload).

Ported from the scratchpad's test_embed_stage.py.
"""

import json
import uuid

import httpx
import pytest

import shared_libs.pipelines.nodes  # noqa: F401 — auto-discovery
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode, EmbedConsumes
from shared_libs.pipelines.nodes.embed.bge_server import EmbedBgeServerConfig, EmbedBgeServerNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Chunk,
    ChunkRole,
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    MetadataFieldSpec,
    SparseVector,
)

CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(),
    name="c",
    supported_formats=["pdf"],
    max_file_size_bytes=1,
    fields=[
        MetadataFieldSpec(
            field_name="keywords",
            field_type=FieldType.KEYWORD_LIST,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.CHUNK,
            semantic=True,
        ),
        MetadataFieldSpec(
            field_name="relevance",
            field_type=FieldType.FLOAT,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.CHUNK,
        ),  # not semantic
        MetadataFieldSpec(
            field_name="summary",
            field_type=FieldType.STRING,
            origin=FieldOrigin.GENERATED,
            scope=FieldScope.DOCUMENT,
            semantic=True,
        ),
    ],
)


def _chunk(n: int, text: str, context: str = "", meta: dict | None = None) -> Chunk:
    return Chunk(
        chunk_id=f"d#c{n}", ordinal=n, text=text, context=context, generated_meta=meta or {}
    )


CHUNKS = [
    _chunk(0, "Cats purr.", context="Section: Animals", meta={"keywords": ["cats", "pets"]}),
    _chunk(1, "Dogs bark."),
    _chunk(2, "Bonds fell.", meta={"keywords": ["finance"], "relevance": 0.9}),
    _chunk(3, "Rain came."),
    _chunk(4, "Sun rose."),
]


@NodeRegistry.register("embed")
class FakeEmbed(BaseEmbedderNode):
    KIND = "test_embed_fake_embed"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.dense_calls: list[list[str]] = []
        self.sparse_calls: list[list[str]] = []

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.dense_calls.append(list(texts))
        return [[float(len(t))] * 100 for t in texts]  # dim 100 -> triggers record strip

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        self.sparse_calls.append(list(texts))
        return [SparseVector(indices=[1, 7], values=[0.5, float(len(t))]) for t in texts]


@NodeRegistry.register("embed")
class FakeDenseOnly(BaseEmbedderNode):
    KIND = "test_embed_fake_dense_only"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] * 100 for _ in texts]


async def test_batching_enriched_text_linkage_and_sparse_present() -> None:
    node = FakeEmbed(
        id="e", config=BaseEmbedConfig(model="fake-m3", batch_size=2, embed_semantic_fields=True)
    )
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings
    assert emb.model == "fake-m3"
    assert emb.dimension == 100
    assert len(emb.items) == 5
    assert len(node.dense_calls) == 3 + 1  # 5 texts / batch 2 = 3 calls (+1 for the keywords field)
    assert node.dense_calls[0][0].startswith("Section: Animals\n\n")  # ENRICHED text embedded
    assert [item.chunk_id for item in emb.items] == [c.chunk_id for c in CHUNKS]  # linked, in order
    assert emb.items[0].sparse is not None
    assert emb.items[0].sparse.indices == [1, 7]


async def test_semantic_chunk_fields_get_named_vectors_only_where_present() -> None:
    node = FakeEmbed(
        id="e", config=BaseEmbedConfig(model="fake-m3", batch_size=2, embed_semantic_fields=True)
    )
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings
    assert set(emb.items[0].fields) == {"keywords"}
    assert set(emb.items[2].fields) == {"keywords"}
    assert emb.items[1].fields == {}
    assert emb.items[3].fields == {}
    field_texts = [t for call in node.dense_calls for t in call if "," in t or t == "finance"]
    assert "cats, pets" in field_texts
    assert "finance" in field_texts  # list rendered as joined text
    # relevance (not semantic) and summary (doc scope) got NO vectors
    assert all("0.9" not in t for call in node.dense_calls for t in call)


async def test_disabled_by_role_chunks_are_not_embedded_but_the_rest_are() -> None:
    # Furniture chunks (header/footer, toc) must incur NO vector spend, yet the body chunks around
    # them embed normally — the vectors are chunk_id-linked, so the disabled ones are simply absent.
    mixed = [
        _chunk(0, "Body one."),
        Chunk(
            chunk_id="d#c1", ordinal=1, text="Confidential — page 1", role=ChunkRole.HEADER_FOOTER
        ),
        _chunk(2, "Body two."),
        Chunk(chunk_id="d#c3", ordinal=3, text="1. Intro .... 1", role=ChunkRole.TOC),
    ]
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="m", batch_size=8))
    out = await node.run(EmbedConsumes(chunks=mixed, contract=CONTRACT))

    # 1. Only the two body chunks got vectors; the furniture chunks are absent from the linkage.
    embedded_ids = {item.chunk_id for item in out.embeddings.items}
    assert embedded_ids == {"d#c0", "d#c2"}
    # 2. No provider call ever saw the furniture text — the cost was truly skipped, not discarded.
    embedded_texts = [t for call in node.dense_calls for t in call]
    assert not any("Confidential" in t or "Intro" in t for t in embedded_texts)


async def test_content_free_placeholder_chunks_are_not_embedded_but_the_rest_are() -> None:
    # A chunk whose enriched text is ONLY a bare "[Image: photo]" marker (a cropped-but-unenriched
    # figure) carries no searchable content: it must get NO vector so it can never surface as a hit
    # with a misleading self-citation. It still flows to persistence (like role-disabled chunks) —
    # it is simply absent from the chunk_id-linked vectors here. The real chunks around it embed.
    mixed = [
        _chunk(0, "Body one."),
        _chunk(1, "[Image: photo]"),  # bare placeholder → no content
        _chunk(2, "   \n [Image: photo]  \n "),  # whitespace + bare marker → still no content
        _chunk(3, "Body two."),
        _chunk(4, "[Image: chart] Figure 2: quarterly revenue"),  # marker WITH caption → real text
    ]
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="m", batch_size=8))
    out = await node.run(EmbedConsumes(chunks=mixed, contract=CONTRACT))

    # 1. Only the chunks with real content got vectors; the bare placeholders are absent.
    embedded_ids = {item.chunk_id for item in out.embeddings.items}
    assert embedded_ids == {"d#c0", "d#c3", "d#c4"}
    # 2. No provider call ever saw a bare placeholder — the cost was truly skipped, not discarded.
    embedded_texts = [t for call in node.dense_calls for t in call]
    assert not any(t.strip() == "[Image: photo]" for t in embedded_texts)


async def test_all_disabled_chunks_yield_empty_embeddings_without_spend() -> None:
    only_furniture = [
        Chunk(chunk_id="d#c0", ordinal=0, text="Header", role=ChunkRole.HEADER_FOOTER),
        Chunk(chunk_id="d#c1", ordinal=1, text="Contents", role=ChunkRole.TOC),
    ]
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="m"))
    out = await node.run(EmbedConsumes(chunks=only_furniture, contract=CONTRACT))
    assert out.embeddings.items == []
    assert node.dense_calls == []  # no batch was ever issued


async def test_embed_semantic_fields_false_disables_per_field_vectors() -> None:
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="m", embed_semantic_fields=False))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert all(item.fields == {} for item in out.embeddings.items)


async def test_dense_only_provider_skips_the_sparse_axis_gracefully() -> None:
    node = FakeDenseOnly(id="e", config=BaseEmbedConfig(model="m"))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert all(item.sparse is None for item in out.embeddings.items)
    assert all(item.dense is not None for item in out.embeddings.items)


def test_family_registration_and_describe_expose_the_ui_contract() -> None:
    assert {"bge_server", "openai_compatible"} <= set(NodeRegistry.kinds("embed"))
    assert EmbedBgeServerNode.describe().unique_in_graph is True
    described = EmbedBgeServerNode.describe()
    for key in (
        "base_url",
        "model",
        "batch_size",
        "embed_sparse",
        "embed_semantic_fields",
    ):
        assert key in described.config_schema["properties"], key


async def test_blob_run_keeps_live_vectors_real_but_the_trace_strips_them() -> None:
    blob = {
        "node_type": "group",
        "id": "embed_stage",
        "nodes": [
            {
                "node_type": "action",
                "id": "embed",
                "family": "embed",
                "kind": "test_embed_fake_embed",
                "config": {"model": "fake-m3", "batch_size": 2},
            }
        ],
        "bindings": {
            "embed": {
                "chunks": {"source": "run", "field_name": "chunks"},
                "contract": {"source": "run", "field_name": "contract"},
            }
        },
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, record = await FlowEngine().execute(group, {"chunks": CHUNKS, "contract": CONTRACT})
    assert output.embeddings.items[0].dense[0] == float(
        len(CHUNKS[0].enriched_text)
    )  # LIVE data real
    dumped = record.children[0].output["embeddings"]["items"][0]
    assert dumped["dense"] == "<100 numbers>"  # the TRACE carries a placeholder


@NodeRegistry.register("embed")
class FlakyThenOk(BaseEmbedderNode):
    """Dense hook that raises a transient timeout the first ``fail_times`` calls, then succeeds."""

    KIND = "test_embed_flaky_then_ok"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, fail_times: int = 0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._fail_times = fail_times
        self.calls = 0

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise httpx.ReadTimeout("simulated transient timeout")
        return [[float(len(t))] for t in texts]


@NodeRegistry.register("embed")
class FlakyBySize(BaseEmbedderNode):
    """Dense hook that fails (transient) on any batch larger than ``max_ok`` — forces adaptive split."""

    KIND = "test_embed_flaky_by_size"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, max_ok: int = 2, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._max_ok = max_ok
        self.largest_success = 0

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > self._max_ok:
            raise httpx.ConnectError("simulated overload on a large batch")
        self.largest_success = max(self.largest_success, len(texts))
        return [[float(len(t))] for t in texts]


@NodeRegistry.register("embed")
class HardFail(BaseEmbedderNode):
    """Dense hook that raises a NON-transient error — must not be retried or split."""

    KIND = "test_embed_hard_fail"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls = 0

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        raise ValueError("permanent, not transient")


async def test_transient_error_is_retried_then_succeeds_without_losing_the_document() -> None:
    # Two timeouts then success: the whole document still embeds — the old behaviour lost every
    # vector on the first timeout. batch_size=8 keeps all five chunks in one batch (one retry chain).
    node = FlakyThenOk(
        id="e",
        config=BaseEmbedConfig(
            model="m", batch_size=8, embed_sparse=False, retry_backoff_seconds=0.0
        ),
        fail_times=2,
    )
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert len(out.embeddings.items) == 5  # nothing dropped
    assert node.calls == 3  # 2 transient failures + 1 success


async def test_persistent_large_batch_failure_splits_adaptively_until_it_succeeds() -> None:
    # A batch too large to embed keeps failing; halving it (5 -> 2+3 -> 1+2) eventually succeeds and
    # every chunk gets a vector. The largest batch that ever succeeded is <= the tolerated size.
    node = FlakyBySize(
        id="e",
        config=BaseEmbedConfig(
            model="m", batch_size=8, embed_sparse=False, max_retries=1, retry_backoff_seconds=0.0
        ),
        max_ok=2,
    )
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert len(out.embeddings.items) == 5  # all recovered via splitting
    assert node.largest_success <= 2


async def test_non_transient_error_is_raised_immediately_without_retry_or_split() -> None:
    node = HardFail(
        id="e",
        config=BaseEmbedConfig(
            model="m", batch_size=8, embed_sparse=False, retry_backoff_seconds=0.0
        ),
    )
    with pytest.raises(ValueError, match="permanent"):
        await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert node.calls == 1  # no retry, no split for a non-transient error


async def test_max_retries_zero_preserves_one_shot_behaviour() -> None:
    # Opt-out: max_retries=0 must not retry and must not split — a single timeout propagates at once.
    node = FlakyThenOk(
        id="e",
        config=BaseEmbedConfig(model="m", batch_size=8, embed_sparse=False, max_retries=0),
        fail_times=1,
    )
    with pytest.raises(httpx.ReadTimeout):
        await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert node.calls == 1


def _mock_bge_transport(calls: list[str]) -> httpx.MockTransport:
    """A MockTransport answering the bge_server routes, recording every path it served."""

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["inputs"]
        calls.append(request.url.path)
        if request.url.path == "/embed":
            return httpx.Response(200, json=[[0.2] * 8 for _ in inputs])
        if request.url.path == "/embed_sparse":
            return httpx.Response(200, json=[[{"index": 1, "value": 0.5}] for _ in inputs])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_bge_server_hits_the_dense_and_sparse_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real bge_server node, HTTP mocked: it POSTs /embed for dense and /embed_sparse for the
    # lexical axis, filling both per chunk.
    calls: list[str] = []
    transport = _mock_bge_transport(calls)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: original_client(*a, **{**k, "transport": transport})
    )

    node = EmbedBgeServerNode(id="e", config=EmbedBgeServerConfig(base_url="http://bge", model="m"))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings

    assert "/embed" in calls
    assert "/embed_sparse" in calls
    assert [i.chunk_id for i in emb.items] == [c.chunk_id for c in CHUNKS]
    assert all(item.dense is not None and item.sparse is not None for item in emb.items)


@NodeRegistry.register("embed")
class FakeCombined(BaseEmbedderNode):
    """Provider with a single-pass combined route; records every hook it is asked to run."""

    KIND = "test_embed_fake_combined"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.dense_calls: list[list[str]] = []
        self.sparse_calls: list[list[str]] = []
        self.combined_calls: list[list[str]] = []

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        self.dense_calls.append(list(texts))
        return [[float(len(t))] * 100 for t in texts]

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        self.sparse_calls.append(list(texts))
        return [SparseVector(indices=[1, 7], values=[0.5, float(len(t))]) for t in texts]

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        self.combined_calls.append(list(texts))
        dense = [[float(len(t))] * 100 for t in texts]
        sparse = [SparseVector(indices=[1, 7], values=[0.5, float(len(t))]) for t in texts]
        return dense, sparse


@NodeRegistry.register("embed")
class FakeCombinedUnsupported(FakeCombined):
    """Combined route absent (returns None, as a 404 maps to) — the caller must fall back."""

    KIND = "test_embed_fake_combined_unsupported"

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        self.combined_calls.append(list(texts))
        return None


@NodeRegistry.register("embed")
class FakeCombinedFlakyBySize(BaseEmbedderNode):
    """Combined hook that fails (transient) on any batch larger than ``max_ok`` — forces the split."""

    KIND = "test_embed_combined_flaky_by_size"
    NAME = "F"
    SUMMARY = "t"
    Config = BaseEmbedConfig

    def __init__(self, *args, max_ok: int = 2, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._max_ok = max_ok
        self.largest_success = 0

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]  # unused: the combined route is always supported

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        if len(texts) > self._max_ok:
            raise httpx.ConnectError("simulated overload on a large combined batch")
        self.largest_success = max(self.largest_success, len(texts))
        dense = [[float(len(t))] for t in texts]
        sparse = [SparseVector(indices=[len(t)], values=[float(len(t))]) for t in texts]
        return dense, sparse


async def test_combined_route_used_once_per_batch_without_the_separate_hooks() -> None:
    # When a provider exposes the single-pass combined hook, each batch is embedded through it ONCE
    # and the separate dense/sparse hooks are never touched — same vectors as the separate path.
    node = FakeCombined(id="e", config=BaseEmbedConfig(model="m", batch_size=2))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings

    assert [len(c) for c in node.combined_calls] == [
        2,
        2,
        1,
    ]  # 5 texts / batch 2 = 3 combined calls
    assert node.dense_calls == [] and node.sparse_calls == []  # the separate routes were untouched
    assert len(emb.items) == 5
    assert emb.items[0].dense == [float(len(CHUNKS[0].enriched_text))] * 100
    assert emb.items[0].sparse is not None and emb.items[0].sparse.indices == [1, 7]


async def test_combined_unsupported_falls_back_and_is_not_reprobed() -> None:
    # A None from the combined hook (an old server's 404) drops the run to the separate hooks — and
    # the combined hook is probed only ONCE, never again for the later batches.
    node = FakeCombinedUnsupported(id="e", config=BaseEmbedConfig(model="m", batch_size=2))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings

    assert len(node.combined_calls) == 1  # probed once, then remembered as unsupported
    assert [len(c) for c in node.dense_calls] == [
        2,
        2,
        1,
    ]  # every batch fell back to separate dense
    assert [len(c) for c in node.sparse_calls] == [2, 2, 1]
    assert len(emb.items) == 5
    assert all(item.dense is not None and item.sparse is not None for item in emb.items)


async def test_combined_route_split_preserves_order_on_both_axes() -> None:
    # A batch too large for the combined hook keeps failing; halving it (5 -> 2+3 -> 1+2) recovers,
    # and the halves' dense AND sparse lists are concatenated back in the original chunk order.
    node = FakeCombinedFlakyBySize(
        id="e",
        config=BaseEmbedConfig(model="m", batch_size=8, max_retries=1, retry_backoff_seconds=0.0),
        max_ok=2,
    )
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings

    assert node.largest_success <= 2  # never succeeded on a batch above the tolerated size
    assert len(emb.items) == 5
    for item, chunk in zip(emb.items, CHUNKS, strict=True):
        length = float(len(chunk.enriched_text))
        assert item.dense == [length]  # dense aligned 1:1 after the split
        assert item.sparse is not None and item.sparse.values == [length]  # sparse aligned too


def _mock_bge_combined_transport(calls: list[str]) -> httpx.MockTransport:
    """A MockTransport serving the combined /embed_all route and 404-ing the separate ones."""

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["inputs"]
        calls.append(request.url.path)
        if request.url.path == "/embed_all":
            return httpx.Response(
                200,
                json={
                    "dense": [[0.2] * 8 for _ in inputs],
                    "sparse": [[{"index": 1, "value": 0.5}] for _ in inputs],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def test_bge_server_uses_embed_all_single_pass_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real bge_server node, HTTP mocked: /embed_all serves both axes in one pass, so the separate
    # /embed and /embed_sparse routes are never called.
    calls: list[str] = []
    transport = _mock_bge_combined_transport(calls)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: original_client(*a, **{**k, "transport": transport})
    )

    node = EmbedBgeServerNode(id="e", config=EmbedBgeServerConfig(base_url="http://bge", model="m"))
    out = await node.run(EmbedConsumes(chunks=CHUNKS, contract=CONTRACT))
    emb = out.embeddings

    assert "/embed_all" in calls
    assert (
        "/embed" not in calls and "/embed_sparse" not in calls
    )  # a single pass, no separate calls
    assert [i.chunk_id for i in emb.items] == [c.chunk_id for c in CHUNKS]
    assert all(item.dense is not None and item.sparse is not None for item in emb.items)


async def test_bge_embed_all_maps_404_to_none_but_propagates_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fallback contract at the provider seam: a 404 (route absent on an old server) becomes None
    # so the caller falls back; a 5xx or a timeout still RAISES so the resilient retry/split applies.
    original_client = httpx.AsyncClient

    def install(handler) -> EmbedBgeServerNode:
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: original_client(*a, **{**k, "transport": transport}),
        )
        return EmbedBgeServerNode(
            id="e", config=EmbedBgeServerConfig(base_url="http://bge", model="m")
        )

    absent = install(lambda request: httpx.Response(404))
    assert await absent._embed_dense_sparse(["x"]) is None  # unsupported → None, not an error

    server_error = install(lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):  # genuine transient → propagates for retry/split
        await server_error._embed_dense_sparse(["x"])

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout")

    timing_out = install(timeout)
    with pytest.raises(httpx.ReadTimeout):  # timeout must not be swallowed into None
        await timing_out._embed_dense_sparse(["x"])
