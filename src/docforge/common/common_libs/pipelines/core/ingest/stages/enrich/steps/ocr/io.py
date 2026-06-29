# ====== Code Summary ======
# IO contract for the OCR step: it consumes the classified IR (for the document language hint) and
# the seeded work list from the classify step (both via FromSibling), runs OCR over exactly the
# figures the routing marked, and re-emits the work list (now carrying OCR text + traces) plus the
# OCR call / cache-hit counters the stage aggregates.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...figure_work import FigureWork


class IngestStageEnrichStepOcrInput(NodeInput):
    """
    Input of the OCR step.

    Attributes:
        ir (DocumentIR): The classified IR (from the classify step) - used for the language hint.
        figure_works (list[FigureWork]): The seeded per-figure work list (from the classify step).
    """

    ir: Annotated[DocumentIR, FromSibling(producer="classify", field="ir")]
    figure_works: Annotated[
        list[FigureWork], FromSibling(producer="classify", field="figure_works")
    ]


class IngestStageEnrichStepOcrOutput(NodeOutput):
    """
    Output of the OCR step.

    Attributes:
        figure_works (list[FigureWork]): The work list with OCR text + traces folded into the routed
            figures (threaded onward to the VLM step).
        ocr_calls (int): OCR chain invocations (cache misses only).
        ocr_cache_hits (int): OCR results served from the provider-call cache.
    """

    figure_works: list[FigureWork]
    ocr_calls: int = 0
    ocr_cache_hits: int = 0


__all__ = [
    "IngestStageEnrichStepOcrInput",
    "IngestStageEnrichStepOcrOutput",
]
