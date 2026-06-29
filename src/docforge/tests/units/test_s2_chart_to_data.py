# ====== Code Summary ======
# Unit tests for the enrich `chart_to_data` gate, now split across the native steps. The routing
# decision (EnrichRouting) sets `use_chart_schema` IFF a CHART figure runs with chart_to_data on; the
# ChartStep then extracts the structured table (data_table + the chart_extractions counter) IFF that
# decision was taken. Together these reproduce the legacy "CHART with the flag off is described like a
# normal figure (VLM description only, no data_table)" behaviour — without a second provider call.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
)
from common_libs.pipeline.ingest.stages.enrich.routing import EnrichRouting
from common_libs.pipeline.ingest.stages.enrich.scratch import ENRICH_SCRATCH_KEY, EnrichScratch, FigureWork
from common_libs.pipeline.ingest.stages.enrich.steps.chart_step import ChartStep
from common_libs.pipeline.stages.context import PipelineContext


def _chart_work(*, use_chart_schema: bool) -> FigureWork:
    """A CHART FigureWork past the VLM pass, carrying a structured table to mine."""
    return FigureWork(
        block_id="b0",
        crop_key="crop/0",
        crop_bytes=b"crop/0",
        crop_hash="crop/0",
        kind=FigureKind.CHART,
        relevance=0.9,
        decorative=False,
        do_ocr=True,
        do_vlm=True,
        use_chart_schema=use_chart_schema,
        description="a bar chart of revenue per quarter",
        vlm_structured={"table": [["Q1", "10"], ["Q2", "20"]]},
    )


def _ctx(work: FigureWork) -> PipelineContext:
    """A context with a single CHART figure block + a scratch carrying the work item."""
    block = Block(
        id="b0",
        type=BlockType.FIGURE,
        prov=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 1.0)),
        reading_order=0,
        figure=FigureEnrichment(kind=FigureKind.CHART, crop_key="crop/0", relevance=0.9),
    )
    ir = DocumentIR(doc_id="d1", source_hash="h", n_pages=1, language="en", blocks=[block])
    ctx = PipelineContext(ir=ir)
    scratch = EnrichScratch(language="en")
    scratch.figures = {"b0": work}
    ctx.aux[ENRICH_SCRATCH_KEY] = scratch
    return ctx


# ─── routing gate ─────────────────────────────────────────────────────────────────────────────


def test_routing_sets_chart_schema_only_when_flag_on() -> None:
    """A CHART requests the chart schema iff chart_to_data is on; other kinds never do."""
    on = EnrichRouting.decide(FigureKind.CHART, ocr_enabled=True, vlm_enabled=True, chart_to_data=True)
    off = EnrichRouting.decide(FigureKind.CHART, ocr_enabled=True, vlm_enabled=True, chart_to_data=False)
    diagram = EnrichRouting.decide(FigureKind.DIAGRAM, ocr_enabled=True, vlm_enabled=True, chart_to_data=True)
    assert on.use_chart_schema is True
    assert off.use_chart_schema is False
    assert diagram.use_chart_schema is False  # DIAGRAM is never a chart-to-data target


# ─── chart extraction step ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chart_to_data_enabled_extracts_table() -> None:
    """With the chart schema routed, the ChartStep mines a data_table and ticks the counter."""
    ctx = _ctx(_chart_work(use_chart_schema=True))

    await ChartStep().run(ctx)

    scratch = ctx.aux[ENRICH_SCRATCH_KEY]
    assert scratch.figures["b0"].data_table == [["Q1", "10"], ["Q2", "20"]]
    assert scratch.counters.chart_extractions == 1
    # The data table also lands on the rebuilt IR figure block.
    assert ctx.ir.blocks[0].figure.data_table == [["Q1", "10"], ["Q2", "20"]]


@pytest.mark.asyncio
async def test_chart_to_data_disabled_skips_table() -> None:
    """Without the chart schema, the CHART keeps its VLM description but no data_table is extracted."""
    ctx = _ctx(_chart_work(use_chart_schema=False))

    await ChartStep().run(ctx)

    scratch = ctx.aux[ENRICH_SCRATCH_KEY]
    assert scratch.figures["b0"].data_table is None
    assert scratch.counters.chart_extractions == 0
    assert ctx.ir.blocks[0].figure.data_table is None
