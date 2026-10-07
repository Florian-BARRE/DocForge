"""Replay IR round-trip — a run's IR persisted through the REAL RunTranslator, read back through
the shared IRBundleAdapter (pipeline-scope ids), rebuilds the SAME chunks the original run produced."""

import uuid
from types import SimpleNamespace

from persistence import RunTranslator

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    IntakeResult,
    Provenance,
    RunBundle,
)
from shared_libs.services.db.facades import IRBundle, IRBundleAdapter


def _ir() -> DocumentIR:
    def block(i: int, kind: BlockType, text: str | None, **extra) -> Block:
        return Block(
            id=f"b{i}",
            block_type=kind,
            provenance=Provenance(page=0, bbox=(0.0, 0.1 * i, 1.0, 0.1 * i + 0.05)),
            reading_order=i,
            text=text,
            **extra,
        )

    return DocumentIR(
        doc_id="d",
        source_hash="h",
        n_pages=1,
        language="en",
        blocks=[
            block(0, BlockType.HEADING, "Introduction", level=1),
            block(1, BlockType.PARAGRAPH, "Replay re-runs only downstream stages.", parent_id="b0"),
            block(2, BlockType.PARAGRAPH, "The parse stage never runs again.", parent_id="b0"),
            block(
                3,
                BlockType.FIGURE,
                None,
                figure=FigureEnrichment(kind=FigureKind.CHART, description="A bar chart of costs."),
            ),
        ],
    )


async def test_persisted_ir_round_trip_rebuilds_the_same_chunks() -> None:
    group = PipelineBuilder().build(IngestPipeline.default_blob())
    chunker = next(child for child in group.children if child.id == "chunk")
    ir = _ir()
    original = (await chunker.run(chunker.Consumes(ir=ir))).chunks

    # Persist through the REAL translator, then read the rows back through the shared adapter.
    document_id = uuid.uuid4()
    bundle = RunBundle(ingest=IntakeResult(source_hash="h"), ir=ir, chunks=original)
    payload = RunTranslator.translate(document_id, bundle, [], "structure_aware", "x").payload
    document = SimpleNamespace(
        id=document_id, source_hash="h", title="", page_count=1, language="en"
    )
    rows = IRBundle(
        blocks=payload.blocks,
        tables=payload.block_tables,
        figures=payload.block_figures,
        enrichments=payload.enrichments,
    )
    rebuilt = IRBundleAdapter.to_document_ir(document, rows, pipeline_ids=True)

    assert [block.id for block in rebuilt.blocks] == [block.id for block in ir.blocks]
    replayed = (await chunker.run(chunker.Consumes(ir=rebuilt))).chunks
    assert [(c.text, c.block_ids) for c in replayed] == [(c.text, c.block_ids) for c in original]
