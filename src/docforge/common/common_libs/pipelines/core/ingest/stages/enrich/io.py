# ====== Code Summary ======
# IO contract for the enrich stage: its input is the parsed ``ir`` (read from the parse sibling); its
# output is the enriched ``ir`` (FIGURE blocks classified + OCR/VLM/chart-enriched in place) plus the
# EnrichResult carrying the per-run counts. The enriched ``ir`` is what the downstream chunk stage
# consumes.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .result import EnrichResult


class IngestStageEnrichInput(NodeInput):
    """
    Input of the enrich stage (read from the parse sibling).

    Attributes:
        ir (DocumentIR): The parsed canonical IR produced by the parse stage.
    """

    ir: Annotated[DocumentIR, FromSibling(producer="parse", field="ir")]


class IngestStageEnrichOutput(NodeOutput):
    """
    Output of the enrich stage - the enriched IR + the per-run counts.

    Attributes:
        ir (DocumentIR): The IR with every enrichable FIGURE block enriched in place.
        enrich_result (EnrichResult): The enriched IR + classifier/OCR/VLM/chart counters.
    """

    ir: DocumentIR
    enrich_result: EnrichResult


__all__ = ["IngestStageEnrichInput", "IngestStageEnrichOutput"]
