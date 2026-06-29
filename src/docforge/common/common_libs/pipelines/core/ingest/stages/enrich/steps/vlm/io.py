# ====== Code Summary ======
# IO contract for the VLM step: it consumes the work list from the OCR step (via FromSibling) -
# grounding each VLM call on the OCR text recorded there - runs the VLM over exactly the figures the
# routing marked, and re-emits the work list (now carrying the VLM description + raw structured
# output, which the chart step later mines) plus the VLM call / cache-hit counters.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...figure_work import FigureWork


class IngestStageEnrichStepVlmInput(NodeInput):
    """
    Input of the VLM step.

    Attributes:
        figure_works (list[FigureWork]): The work list from the OCR step (carries OCR grounding text).
    """

    figure_works: Annotated[
        list[FigureWork], FromSibling(producer="ocr", field="figure_works")
    ]


class IngestStageEnrichStepVlmOutput(NodeOutput):
    """
    Output of the VLM step.

    Attributes:
        figure_works (list[FigureWork]): The work list with the VLM description + raw structured
            output folded into the routed figures (threaded onward to the chart step).
        vlm_calls (int): VLM chain invocations (cache misses only).
        vlm_cache_hits (int): VLM results served from the provider-call cache.
    """

    figure_works: list[FigureWork]
    vlm_calls: int = 0
    vlm_cache_hits: int = 0


__all__ = [
    "IngestStageEnrichStepVlmInput",
    "IngestStageEnrichStepVlmOutput",
]
