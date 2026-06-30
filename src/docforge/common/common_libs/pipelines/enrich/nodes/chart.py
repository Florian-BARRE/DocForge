# ====== Code Summary ======
# The chart node - the last action of the enrich stage. It calls NO provider: the structured chart
# output was already produced by the single VLM call in the VLM node (chart-to-data is a parameter of
# that call, not a second one). This node mines the raw VLM structured output on each FigureWork (for
# the CHART figures the routing marked with the chart schema) into a row-major data table, counts the
# extractions exactly as the legacy path did, and re-emits the final work list. When chart-to-data is
# off, no figure carries ``use_chart_schema`` and the work list is passed through unchanged.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.core.ingest.stages.enrich.figure_work import FigureWork
from common_libs.pipelines.flow import ActionNode, Context, FromNode, NodeInput, NodeOutput


class EnrichChartInput(NodeInput):
    """Input of the chart node - the work list from the VLM node (carries the raw structured output)."""

    figure_works: Annotated[list[FigureWork], FromNode("vlm", "figure_works")]


class EnrichChartOutput(NodeOutput):
    """Output of the chart node - the final work list with chart data tables folded in + the count."""

    figure_works: list[FigureWork]
    chart_extractions: int = 0


class EnrichChart(ActionNode):
    """Extract structured data tables from the chart figures' VLM output (pure post-processing)."""

    Input = EnrichChartInput
    Output = EnrichChartOutput

    async def execute(self, ctx: Context) -> EnrichChartOutput:
        """
        Mine the VLM structured output of every chart-schema figure into a data table.

        Args:
            ctx (Context): The resolved input (the work list); no service is used.

        Returns:
            EnrichChartOutput: The final work list + the extraction count.
        """
        # 1. Only figures routed with the chart schema AND with a VLM structured payload qualify
        # (mirrors the legacy ``use_chart_schema and vlm_result.structured`` guard).
        works = ctx.input.figure_works
        extractions = 0
        for work in works:
            if not (work.use_chart_schema and work.vlm_structured):
                continue
            data_table = self._extract_table(work)
            if data_table:
                work.data_table = data_table
                extractions += 1

        self.logger.info(f"Enrich chart-to-data done: extractions={extractions}")
        return EnrichChartOutput(figure_works=works, chart_extractions=extractions)

    @staticmethod
    def _extract_table(work: FigureWork) -> list[list[str]] | None:
        """
        Convert the VLM structured ``table`` payload into a row-major string table.

        Args:
            work (FigureWork): The figure whose VLM structured output is mined.

        Returns:
            list[list[str]] | None: The row-major table, or None when the payload carries no usable
                list-of-rows (byte-identical to the legacy extraction).
        """
        raw_table = work.vlm_structured.get("table")
        if not (raw_table and isinstance(raw_table, list)):
            return None
        data_table = [[str(cell) for cell in row] for row in raw_table if isinstance(row, list)]
        return data_table or None


__all__ = ["EnrichChart", "EnrichChartInput", "EnrichChartOutput"]
