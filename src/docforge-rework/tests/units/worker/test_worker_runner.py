"""PipelineRunner: the RunBundle output contract, fresh run inputs, and loud failures.

Ported from the scratchpad's test_worker_runner.py. ``worker/backend/libs`` is already on
sys.path courtesy of the root conftest (see [[bootstrap-mechanics]]) so ``runner`` imports as a
top-level package here, no extra bootstrap needed.
"""

import uuid

import pytest
from runner import PipelineRunError, PipelineRunner

import shared_libs.pipelines.ingest.nodes  # noqa: F401 — registers deliver/bundle
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    Chunk,
    ChunkEmbeddings,
    CollectionContract,
    DocumentIR,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRenders,
    SourceDocument,
)


@NodeRegistry.register("deliver")
class FakeProduceAll(ActionNode):
    """Produces every persistable RunBundle slot in one hop, so bundle can close the run."""

    KIND = "test_worker_runner_produce_all"
    NAME = "F"
    SUMMARY = "t"
    Config = NodeConfig

    class Consumes(NodeInput):
        source: SourceDocument

    class Produces(NodeOutput):
        ingest: IntakeResult
        ir: DocumentIR
        pages: PageRenders
        chunks: list[Chunk]
        document_meta: GeneratedDocumentMeta
        embeddings: ChunkEmbeddings

    async def run(self, data: "FakeProduceAll.Consumes") -> "FakeProduceAll.Produces":
        if data.source.filename == "boom.pdf":
            raise RuntimeError("stage exploded")
        return self.Produces(
            ingest=IntakeResult(source_hash="h", pdf_content=None, page_count=3),
            ir=DocumentIR(doc_id="d", source_hash="h", n_pages=3, blocks=[]),
            pages=PageRenders(pages=[]),
            chunks=[Chunk(chunk_id="d#c0", ordinal=0, text=data.source.filename)],
            document_meta=GeneratedDocumentMeta(values={"summary": "ok"}),
            embeddings=ChunkEmbeddings(model="m", dimension=2, items=[]),
        )


BLOB = {
    "node_type": "group",
    "id": "mini_ingest",
    "nodes": [
        {"node_type": "action", "id": "produce", "family": "deliver",
         "kind": "test_worker_runner_produce_all", "config": {}},
        {"node_type": "action", "id": "bundle", "family": "deliver", "kind": "bundle", "config": {}},
    ],
    "transitions": [{"from_node_id": "produce", "to_node_id": "bundle"}],
    "bindings": {
        "produce": {"source": {"source": "run", "field_name": "source"}},
        "bundle": {slot: {"source": "node", "node_id": "produce", "field_name": slot}
                   for slot in ("ingest", "ir", "pages", "chunks", "document_meta", "embeddings")},
    },
}


@pytest.fixture
def contract() -> CollectionContract:
    return CollectionContract(
        collection_id=uuid.uuid4(), name="c", supported_formats=["pdf"], max_file_size_bytes=10
    )


@pytest.fixture
def runner() -> PipelineRunner:
    return PipelineRunner()


async def test_happy_path_delivers_bundle_and_full_trace(runner, contract) -> None:
    source = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    bundle, record = await runner.run(BLOB, source, contract, timeout_seconds=30)
    assert bundle.chunks[0].text == "r.pdf"
    assert bundle.ingest.page_count == 3
    assert record.status.value == "success"
    assert len(record.children) == 2


async def test_fresh_run_input_per_call_no_bleed_between_runs(runner, contract) -> None:
    source_a = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    source_b = SourceDocument(filename="other.pdf", content=b"y", declared_meta={})
    bundle_a, _ = await runner.run(BLOB, source_a, contract, timeout_seconds=30)
    bundle_b, _ = await runner.run(BLOB, source_b, contract, timeout_seconds=30)
    assert bundle_a.chunks[0].text == "r.pdf"
    assert bundle_b.chunks[0].text == "other.pdf"


async def test_invalid_graph_is_rejected_before_any_spend(runner, contract) -> None:
    source = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    bad = dict(BLOB)
    bad["bindings"] = {"produce": {}, "bundle": BLOB["bindings"]["bundle"]}
    with pytest.raises(PipelineRunError, match="missing_binding"):
        await runner.run(bad, source, contract, timeout_seconds=30)


async def test_failed_run_surfaces_the_engine_error(runner, contract) -> None:
    source = SourceDocument(filename="boom.pdf", content=b"x", declared_meta={})
    with pytest.raises(PipelineRunError, match="failed"):
        await runner.run(BLOB, source, contract, timeout_seconds=30)


async def test_output_contract_rejects_a_pipeline_not_ending_on_bundle(runner, contract) -> None:
    source = SourceDocument(filename="r.pdf", content=b"x", declared_meta={})
    no_bundle = {
        "node_type": "group",
        "id": "no_delivery",
        "nodes": [{"node_type": "action", "id": "produce", "family": "deliver",
                   "kind": "test_worker_runner_produce_all", "config": {}}],
        "bindings": {"produce": {"source": {"source": "run", "field_name": "source"}}},
    }
    with pytest.raises(PipelineRunError, match="RunBundle"):
        await runner.run(no_bundle, source, contract, timeout_seconds=30)
