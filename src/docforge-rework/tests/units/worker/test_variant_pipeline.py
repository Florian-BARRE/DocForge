"""Variant ingestion pipelines: the RunBundle's optional slots (pages/document_meta/embeddings)
stay unbound when render/metagen/embed are absent — the graph still validates, runs, and
translates end to end. Ported from the scratchpad's test_variant_pipeline.py.
"""

import uuid

import pytest
from persistence import RunTranslator
from runner import PipelineRunner

import shared_libs.pipelines.ingest.nodes  # noqa: F401
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import (
    Block,
    BlockType,
    Chunk,
    CollectionContract,
    DocumentIR,
    IntakeResult,
    Provenance,
    SourceDocument,
)


@NodeRegistry.register("deliver")
class FakeMinimalProducer(ActionNode):
    """A minimal parse-ish producer: only ingest/ir/chunks — no render/metagen/embed."""

    KIND = "test_variant_pipeline_minimal"
    NAME = "F"
    SUMMARY = "t"
    Config = NodeConfig

    class Consumes(NodeInput):
        source: SourceDocument

    class Produces(NodeOutput):
        ingest: IntakeResult
        ir: DocumentIR
        chunks: list[Chunk]

    async def run(self, data: "FakeMinimalProducer.Consumes") -> "FakeMinimalProducer.Produces":
        ir = DocumentIR(
            doc_id="d",
            source_hash="h",
            n_pages=1,
            blocks=[
                Block(
                    id="b0",
                    block_type=BlockType.PARAGRAPH,
                    reading_order=0,
                    text="Cats.",
                    provenance=Provenance(page=0, bbox=(0, 0, 1, 1)),
                ),
            ],
        )
        return self.Produces(
            ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=1),
            ir=ir,
            chunks=[
                Chunk(chunk_id="d#c0", ordinal=0, text="Cats.", block_ids=["b0"], token_count=2)
            ],
        )


# A MINIMAL pipeline: produce -> bundle. NO render, NO metagen, NO embed: pages/document_meta/
# embeddings stay UNBOUND (optional slots on the bundle node's Consumes).
BLOB = {
    "node_type": "group",
    "id": "minimal_ingest",
    "nodes": [
        {
            "node_type": "action",
            "id": "produce",
            "family": "deliver",
            "kind": "test_variant_pipeline_minimal",
            "config": {},
        },
        {
            "node_type": "action",
            "id": "bundle",
            "family": "deliver",
            "kind": "bundle",
            "config": {},
        },
    ],
    "transitions": [{"from_node_id": "produce", "to_node_id": "bundle"}],
    "bindings": {
        "produce": {"source": {"source": "run", "field_name": "source"}},
        "bundle": {
            slot: {"source": "node", "node_id": "produce", "field_name": slot}
            for slot in ("ingest", "ir", "chunks")
        },
    },
}


def test_variant_with_optional_slots_unbound_validates_clean() -> None:
    issues = GraphValidator().validate(PipelineBuilder().build(BLOB))
    assert issues == []


def test_variant_with_a_required_slot_unbound_is_still_refused() -> None:
    bad = dict(BLOB)
    bad["bindings"] = {
        "produce": BLOB["bindings"]["produce"],
        "bundle": {
            "ingest": BLOB["bindings"]["bundle"]["ingest"],
            "chunks": BLOB["bindings"]["bundle"]["chunks"],
        },  # 'ir' missing — a REQUIRED slot
    }
    issues = GraphValidator().validate(PipelineBuilder().build(bad))
    assert any(
        issue.code.value == "missing_binding" and "'ir'" in issue.message for issue in issues
    )


@pytest.fixture
def contract() -> CollectionContract:
    return CollectionContract(
        collection_id=uuid.uuid4(), name="c", supported_formats=["pdf"], max_file_size_bytes=10
    )


async def test_variant_runs_end_to_end_and_delivers_absent_slots_as_none(contract) -> None:
    source = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    bundle, _record = await PipelineRunner().run(BLOB, source, contract, timeout_seconds=30)
    assert bundle.pages is None
    assert bundle.document_meta is None
    assert bundle.embeddings is None
    assert bundle.chunks[0].text == "Cats."


async def test_variant_translates_skipping_absent_sections_with_no_qdrant_points(contract) -> None:
    source = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    bundle, _record = await PipelineRunner().run(BLOB, source, contract, timeout_seconds=30)
    out = RunTranslator.translate(uuid.uuid4(), bundle, schema=[], strategy="none", config_hash="v")
    assert out.payload.pages == []
    assert out.payload.document_metadata == []
    assert out.points == []
    assert out.dense_dim == 0
    assert out.objects == []
    assert len(out.payload.blocks) == 1
    assert len(out.payload.chunks) == 1
