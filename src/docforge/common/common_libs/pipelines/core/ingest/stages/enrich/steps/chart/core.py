# ====== Code Summary ======
# IngestStageEnrichStepChart - the chart-to-data enrich pass. It does NOT call any provider: the
# structured chart output was already produced by the single VLM call in the VLM step (chart-to-data
# is a parameter of that call, not a second one). This step mines the raw VLM structured output on
# each FigureWork (for the CHART figures the routing marked with the chart schema) into a row-major
# data table, counts the extractions exactly as the legacy ``maybe_vlm`` did, and re-emits the final
# work list. When chart-to-data is off, no figure carries ``use_chart_schema`` and the work list is
# passed through unchanged.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ...figure_work import FigureWork
from ..base import IngestStageEnrichStepBase
from .context import IngestStageEnrichStepChartContext
from .errors import IngestStageEnrichStepChartError
from .io import IngestStageEnrichStepChartInput, IngestStageEnrichStepChartOutput


class IngestStageEnrichStepChart(IngestStageEnrichStepBase):
    """
    Extract structured data tables from the chart figures' VLM output.

    Reads the work list; folds each chart figure's ``data_table`` into its FigureWork and re-emits the
    final work list (with the extraction count). Pure post-processing - no provider call.
    """

    SPEC = NodeSpec(
        key="chart",
        name="Chart-to-data",
        description="Extract structured data tables from the CHART figures' vision-language output.",
    )
    Input = IngestStageEnrichStepChartInput
    Output = IngestStageEnrichStepChartOutput
    Context = IngestStageEnrichStepChartContext
    Error = IngestStageEnrichStepChartError

    async def execute(
        self, ctx: IngestStageEnrichStepChartContext
    ) -> IngestStageEnrichStepChartOutput:
        """
        Mine the VLM structured output of every chart-schema figure into a data table.

        Args:
            ctx (IngestStageEnrichStepChartContext): The chart input (the work list).

        Returns:
            IngestStageEnrichStepChartOutput: The final work list + the extraction count.
        """
        works = ctx.input.figure_works

        # 1. Only figures routed with the chart schema AND with a VLM structured payload qualify
        # (mirrors the legacy ``use_chart_schema and vlm_result.structured`` guard).
        extractions = 0
        for work in works:
            if not (work.use_chart_schema and work.vlm_structured):
                continue
            data_table = self._extract_table(work)
            if data_table:
                work.data_table = data_table
                extractions += 1

        self.logger.info(f"Enrich chart-to-data done: extractions={extractions}")
        return IngestStageEnrichStepChartOutput(figure_works=works, chart_extractions=extractions)

    @staticmethod
    def _extract_table(work: FigureWork) -> list[list[str]] | None:
        """
        Convert the VLM structured ``table`` payload into a row-major string table.

        Args:
            work (FigureWork): The figure whose VLM structured output is mined.

        Returns:
            list[list[str]] | None: The row-major table, or None when the payload carries no usable
                list-of-rows (byte-identical to the legacy ``maybe_vlm`` extraction).
        """
        raw_table = work.vlm_structured.get("table")
        if not (raw_table and isinstance(raw_table, list)):
            return None
        data_table = [
            [str(cell) for cell in row] for row in raw_table if isinstance(row, list)
        ]
        return data_table or None


__all__ = ["IngestStageEnrichStepChart"]
