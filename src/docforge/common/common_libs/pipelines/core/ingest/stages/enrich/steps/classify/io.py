# ====== Code Summary ======
# IO contract for the classify step: it reads the enrich stage's ``ir`` (down from the parent) and
# produces the classified IR plus the seeded per-figure work list (one FigureWork per enrichable
# figure, carrying its routing decision) that the downstream OCR / VLM / chart steps thread through.
# It also surfaces the classifier call / cache-hit / processed counters the stage aggregates.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromParent, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...figure_work import FigureWork


class IngestStageEnrichStepClassifyInput(NodeInput):
    """
    Input of the classify step.

    Attributes:
        ir (DocumentIR): The parsed IR (down from the enrich stage's input).
    """

    ir: Annotated[DocumentIR, FromParent(field="ir")]


class IngestStageEnrichStepClassifyOutput(NodeOutput):
    """
    Output of the classify step.

    Attributes:
        ir (DocumentIR): The IR with each enrichable figure classified (decorative figures final).
        figure_works (list[FigureWork]): One work item per enrichable figure, in document order.
        classifier_calls (int): Classifier chain invocations (cache misses only).
        classifier_cache_hits (int): Classifier results served from the provider-call cache.
        figures_processed (int): FIGURE blocks that completed classification.
    """

    ir: DocumentIR
    figure_works: list[FigureWork]
    classifier_calls: int = 0
    classifier_cache_hits: int = 0
    figures_processed: int = 0


__all__ = [
    "IngestStageEnrichStepClassifyInput",
    "IngestStageEnrichStepClassifyOutput",
]
