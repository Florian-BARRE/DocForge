# ====== Code Summary ======
# ChartStep — the chart-to-data enrich pass, built only when ``enrich.chart_to_data`` is on. It does
# NOT call any provider: the structured chart output was already produced by the single VLM call in
# VlmStep (chart-to-data is a parameter of that call, not a second one). This step mines the raw VLM
# structured output stashed on each FigureWork (for the CHART figures the routing marked with the
# chart schema) into a row-major data table, ticks the chart_extractions counter exactly as the legacy
# ``maybe_vlm`` did, and commits the IR with the tables folded into the figure enrichments.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..ir_writer import EnrichIRWriter
from ..scratch import ENRICH_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext

    from ..scratch import FigureWork


class ChartStep(IngestStep):
    """
    Native enrich step — extracts structured data tables from the chart figures' VLM output.

    Reads ``ir`` + ``ctx.aux["enrich_scratch"]``; writes each chart figure's ``data_table`` onto its
    FigureWork and commits the updated ``ir`` + ``enrich_result``. Pure post-processing of the VLM
    structured output — no provider call.
    """

    KEY: ClassVar[str] = "chart"
    NAME: ClassVar[str] = "Chart-to-data"
    DESCRIPTION: ClassVar[str] = (
        "Extract structured data tables from the CHART figures' vision-language model output."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir", ENRICH_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", "enrich_result")

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Mine the VLM structured output of every chart-schema figure into a data table.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        scratch = ctx.aux[ENRICH_SCRATCH_KEY]

        # 1. Only figures routed with the chart schema AND with a VLM structured payload qualify
        # (mirrors the legacy ``use_chart_schema and vlm_result.structured`` guard).
        for work in scratch.figures.values():
            if not (work.use_chart_schema and work.vlm_structured):
                continue
            data_table = self._extract_table(work)
            if data_table:
                work.data_table = data_table
                scratch.counters.chart_extractions += 1

        # 2. Commit the IR with the extracted data tables folded in.
        EnrichIRWriter.commit(ctx, scratch)

    @staticmethod
    def _extract_table(work: "FigureWork") -> list[list[str]] | None:
        """
        Convert the VLM structured ``table`` payload into a row-major string table.

        Args:
            work (FigureWork): The figure whose VLM structured output is mined.

        Returns:
            list[list[str]] | None: The row-major table, or None when the payload carries no
                usable list-of-rows (byte-identical to the legacy ``maybe_vlm`` extraction).
        """
        raw_table = work.vlm_structured.get("table")
        if not (raw_table and isinstance(raw_table, list)):
            return None
        data_table = [
            [str(cell) for cell in row]
            for row in raw_table
            if isinstance(row, list)
        ]
        return data_table or None


__all__ = ["ChartStep"]
