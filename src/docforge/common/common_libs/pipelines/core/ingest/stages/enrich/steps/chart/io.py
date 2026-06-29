# ====== Code Summary ======
# IO contract for the chart step: it consumes the work list from the VLM step (via FromSibling) and
# re-emits it with a row-major data table mined from each chart figure's VLM structured output, plus
# the count of charts where a table was extracted. Pure post-processing - no service, no provider call.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...figure_work import FigureWork


class IngestStageEnrichStepChartInput(NodeInput):
    """
    Input of the chart step.

    Attributes:
        figure_works (list[FigureWork]): The work list from the VLM step (carries the raw structured
            VLM output to mine).
    """

    figure_works: Annotated[
        list[FigureWork], FromSibling(producer="vlm", field="figure_works")
    ]


class IngestStageEnrichStepChartOutput(NodeOutput):
    """
    Output of the chart step.

    Attributes:
        figure_works (list[FigureWork]): The final work list, with chart data tables folded in.
        chart_extractions (int): Charts where a structured data table was extracted.
    """

    figure_works: list[FigureWork]
    chart_extractions: int = 0


__all__ = [
    "IngestStageEnrichStepChartInput",
    "IngestStageEnrichStepChartOutput",
]
