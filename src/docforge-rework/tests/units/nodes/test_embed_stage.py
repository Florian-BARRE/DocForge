"""Embed stage: batching, dense+sparse, semantic field vectors, chunk linkage, and the trace's
record strip (large numeric vectors compacted to a placeholder — never the raw payload).

Ported from the scratchpad's test_embed_stage.py.
"""

import uuid

import shared_libs.pipelines.nodes  # noqa: F401 — auto-discovery
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode, EmbedConsumes
from shared_libs.pipelines.nodes.embed.bge_server import EmbedBgeServerNode
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
    collection_id=uuid.uuid4(), name="c", supported_formats=["pdf"], max_file_size_bytes=1,
    fields=[
        MetadataFieldSpec(field_name="keywords", field_type=FieldType.KEYWORD_LIST,
                          origin=FieldOrigin.GENERATED, scope=FieldScope.CHUNK, semantic=True),
        MetadataFieldSpec(field_name="relevance", field_type=FieldType.FLOAT,
                          origin=FieldOrigin.GENERATED, scope=FieldScope.CHUNK),  # not semantic
        MetadataFieldSpec(field_name="summary", field_type=FieldType.STRING,
                          origin=FieldOrigin.GENERATED, scope=FieldScope.DOCUMENT, semantic=True),
    ],
)


def _chunk(n: int, text: str, context: str = "", meta: dict | None = None) -> Chunk:
    return Chunk(chunk_id=f"d#c{n}", ordinal=n, text=text, context=context, generated_meta=meta or {})


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
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="fake-m3", batch_size=2, embed_semantic_fields=True))
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
    node = FakeEmbed(id="e", config=BaseEmbedConfig(model="fake-m3", batch_size=2, embed_semantic_fields=True))
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
        Chunk(chunk_id="d#c1", ordinal=1, text="Confidential — page 1", role=ChunkRole.HEADER_FOOTER),
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
    for key in ("base_url", "model", "batch_size", "embed_sparse", "embed_semantic_fields"):
        assert key in described.config_schema["properties"], key


async def test_blob_run_keeps_live_vectors_real_but_the_trace_strips_them() -> None:
    blob = {
        "node_type": "group", "id": "embed_stage",
        "nodes": [{"node_type": "action", "id": "embed", "family": "embed", "kind": "test_embed_fake_embed",
                   "config": {"model": "fake-m3", "batch_size": 2}}],
        "bindings": {"embed": {"chunks": {"source": "run", "field_name": "chunks"},
                               "contract": {"source": "run", "field_name": "contract"}}},
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, record = await FlowEngine().execute(group, {"chunks": CHUNKS, "contract": CONTRACT})
    assert output.embeddings.items[0].dense[0] == float(len(CHUNKS[0].enriched_text))  # LIVE data real
    dumped = record.children[0].output["embeddings"]["items"][0]
    assert dumped["dense"] == "<100 numbers>"  # the TRACE carries a placeholder
