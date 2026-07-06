"""Metagen stage: contract-driven targets, structured schemas, grouping modes, strict coercion,
merge-not-clobber across chained nodes, and loud config errors (unknown/duplicate targets).

Ported from the scratchpad's test_metagen_stage.py.
"""

import uuid

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.nodes.metagen.chunk.core import (
    MetagenChunkConfig,
    MetagenChunkConsumes,
    MetagenChunkNode,
)
from shared_libs.pipelines.ingest.nodes.metagen.document.core import (
    MetagenDocumentConfig,
    MetagenDocumentConsumes,
    MetagenDocumentNode,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Chunk,
    CollectionContract,
    FieldOrigin,
    FieldScope,
    FieldType,
    MetadataFieldSpec,
)


def _spec(name: str, field_type: FieldType, scope: FieldScope) -> MetadataFieldSpec:
    return MetadataFieldSpec(field_name=name, field_type=field_type, origin=FieldOrigin.GENERATED, scope=scope)


CONTRACT = CollectionContract(
    collection_id=uuid.uuid4(),
    name="c", supported_formats=["pdf"], max_file_size_bytes=1,
    fields=[
        MetadataFieldSpec(field_name="title", field_type=FieldType.STRING),  # USER field: ignored
        _spec("summary", FieldType.STRING, FieldScope.DOCUMENT),
        _spec("year", FieldType.INTEGER, FieldScope.DOCUMENT),
        _spec("published_at", FieldType.DATETIME, FieldScope.DOCUMENT),
        _spec("keywords", FieldType.KEYWORD_LIST, FieldScope.CHUNK),
        _spec("relevance", FieldType.FLOAT, FieldScope.CHUNK),
    ],
)
CHUNKS = [
    Chunk(chunk_id="d#c0", ordinal=0, text="Cats purr softly.", context="Section: Animals"),
    Chunk(chunk_id="d#c1", ordinal=1, text="Bonds fell sharply."),
]

# Canned model answers per requested field (raw, pre-coercion).
ANSWERS = {
    "summary": "  A report about cats and bonds. ",
    "year": "2024",                        # str -> int coercion
    "published_at": "2024-03-01T10:00:00",
    "keywords": ["cats", " bonds ", ""],   # cleaned list
    "relevance": "not-a-number",           # uncoercible -> dropped
}


@NodeRegistry.register("metagen")
class FakeDocNode(MetagenDocumentNode):
    KIND = "test_metagen_fake_document"
    NAME = "F"
    SUMMARY = "t"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[tuple, str, str]] = []

    async def _generate(self, schema, system_prompt, text, endpoint):
        self.calls.append((tuple(schema["properties"]), endpoint.model, text))
        return {name: ANSWERS[name] for name in schema["properties"]}


@NodeRegistry.register("metagen")
class FakeChunkNode(MetagenChunkNode):
    KIND = "test_metagen_fake_chunk"
    NAME = "F"
    SUMMARY = "t"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[tuple[tuple, str, str]] = []

    async def _generate(self, schema, system_prompt, text, endpoint):
        self.calls.append((tuple(schema["properties"]), endpoint.model, text))
        if "sharply" in text:
            raise RuntimeError("model 503")
        return {name: ANSWERS[name] for name in schema["properties"]}


async def test_document_scope_combined_is_one_call_with_strict_coercion() -> None:
    node = FakeDocNode(id="d", config=MetagenDocumentConfig(base_url="http://x", model="m-default"))
    out = await node.run(MetagenDocumentConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert out.meta.values == {"summary": "A report about cats and bonds.", "year": 2024,
                               "published_at": "2024-03-01T10:00:00"}
    assert len(node.calls) == 1
    assert set(node.calls[0][0]) == {"summary", "year", "published_at"}
    assert "Cats purr" in node.calls[0][2]
    assert "\n\n" in node.calls[0][2]  # doc view = joined raw texts


async def test_per_field_grouping_and_per_target_model_binding() -> None:
    cfg = MetagenDocumentConfig(
        base_url="http://x", model="m-default", grouping="per_field",
        targets=[
            {"field": "summary", "prompt": "Summarize in one sentence.", "model": "m-big"},
            {"field": "year"},
        ],
    )
    node = FakeDocNode(id="d", config=cfg)
    out = await node.run(MetagenDocumentConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert len(node.calls) == 2  # per_field -> one call per target
    models = {fields[0]: model for fields, model, _ in node.calls}
    assert models == {"summary": "m-big", "year": "m-default"}  # per-target LLM binding
    assert out.meta.values == {"summary": "A report about cats and bonds.", "year": 2024}


async def test_combined_grouping_groups_targets_per_endpoint() -> None:
    cfg = MetagenDocumentConfig(
        base_url="http://x", model="m-default", grouping="combined",
        targets=[{"field": "summary", "model": "m-big"}, {"field": "year"}, {"field": "published_at"}],
    )
    node = FakeDocNode(id="d", config=cfg)
    await node.run(MetagenDocumentConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert len(node.calls) == 2
    assert {tuple(sorted(call[0])) for call in node.calls} == {("summary",), ("published_at", "year")}


async def test_unknown_target_field_fails_loudly_before_any_spend() -> None:
    bad = MetagenDocumentConfig(base_url="http://x", model="m", targets=[{"field": "nope"}])
    with pytest.raises(ValueError, match="nope"):
        await FakeDocNode(id="d", config=bad).run(MetagenDocumentConsumes(chunks=CHUNKS, contract=CONTRACT))


async def test_chunk_scope_uses_enriched_text_and_degrades_per_chunk() -> None:
    node = FakeChunkNode(id="c", config=MetagenChunkConfig(base_url="http://x", model="m"))
    out = await node.run(MetagenChunkConsumes(chunks=CHUNKS, contract=CONTRACT))
    assert out.chunks[0].generated_meta == {"keywords": ["cats", "bonds"]}  # relevance dropped (uncoercible)
    assert out.chunks[1].generated_meta == {}  # 503 -> skip_fields, doc alive
    assert CHUNKS[0].generated_meta == {}  # input copies untouched
    assert any("Section: Animals" in text for _, _, text in node.calls)  # ENRICHED text fed


async def test_chunk_scope_on_error_fail_raises_in_strict_mode() -> None:
    strict = MetagenChunkConfig(base_url="http://x", model="m", on_error="fail")
    with pytest.raises(RuntimeError):
        await FakeChunkNode(id="c", config=strict).run(MetagenChunkConsumes(chunks=CHUNKS, contract=CONTRACT))


async def test_blob_chains_chunk_then_document_metagen() -> None:
    assert {"document", "chunk"} <= set(NodeRegistry.kinds("metagen"))
    assert MetagenChunkNode.describe().unique_in_graph is False  # field-subset instances are legit
    props = MetagenDocumentNode.describe().config_schema["properties"]
    for key in ("targets", "grouping", "system_prompt", "max_document_words", "on_error", "base_url"):
        assert key in props, key

    blob = {
        "node_type": "group", "id": "metagen_stage",
        "nodes": [
            {"node_type": "action", "id": "per_chunk", "family": "metagen", "kind": "test_metagen_fake_chunk",
             "config": {"base_url": "http://x", "model": "m"}},
            {"node_type": "action", "id": "per_doc", "family": "metagen", "kind": "test_metagen_fake_document",
             "config": {"base_url": "http://x", "model": "m"}},
        ],
        "transitions": [{"from_node_id": "per_chunk", "to_node_id": "per_doc"}],
        "bindings": {
            "per_chunk": {"chunks": {"source": "run", "field_name": "chunks"},
                          "contract": {"source": "run", "field_name": "contract"}},
            "per_doc": {"chunks": {"source": "node", "node_id": "per_chunk", "field_name": "chunks"},
                        "contract": {"source": "run", "field_name": "contract"}},
        },
    }
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    output, _record = await FlowEngine().execute(group, {"chunks": CHUNKS, "contract": CONTRACT})
    assert output.meta.values["year"] == 2024


async def test_f1_chained_metagen_nodes_merge_generated_meta_without_clobbering() -> None:
    pre = [CHUNKS[0].model_copy(update={"generated_meta": {"topic": "cats"}})]
    node = FakeChunkNode(id="c", config=MetagenChunkConfig(base_url="http://x", model="m"))
    out = await node.run(MetagenChunkConsumes(chunks=pre, contract=CONTRACT))
    assert out.chunks[0].generated_meta == {"topic": "cats", "keywords": ["cats", "bonds"]}


async def test_f2_duplicate_target_field_is_rejected_loudly() -> None:
    dup = MetagenDocumentConfig(base_url="http://x", model="m",
                                targets=[{"field": "summary"}, {"field": "summary"}])
    with pytest.raises(ValueError, match="more than once"):
        await FakeDocNode(id="d", config=dup).run(MetagenDocumentConsumes(chunks=CHUNKS, contract=CONTRACT))
