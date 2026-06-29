# ====== Code Summary ======
# IO contract for the figure-render step: it consumes the PDF bytes (fetch-pdf, optional), the
# canonical IR (parse), and the degraded flag (parse), and produces the IR with each figure block's
# crop key patched plus the block_id -> crop key map the markdown step records in the ParseResult.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput


class IngestStageParseStepFigureRenderInput(NodeInput):
    """
    Input of the figure-render step.

    Attributes:
        pdf_bytes (bytes | None): The PDF view bytes (from the fetch-pdf step), or None.
        ir (DocumentIR): The canonical IR (from the parse step).
        degraded (bool): The degraded flag (from the parse step) — skip rendering when True.
    """

    pdf_bytes: Annotated[
        bytes | None, FromSibling(producer="fetch_pdf", field="pdf_bytes", required=False)
    ]
    ir: Annotated[DocumentIR, FromSibling(producer="parse", field="ir")]
    degraded: Annotated[bool, FromSibling(producer="parse", field="degraded")]


class IngestStageParseStepFigureRenderOutput(NodeOutput):
    """
    Output of the figure-render step.

    Attributes:
        ir (DocumentIR): The IR with each figure block's ``crop_key`` patched.
        figure_crop_keys (dict[str, str]): block_id -> object-store key for each rendered crop.
    """

    ir: DocumentIR
    figure_crop_keys: dict[str, str]


__all__ = [
    "IngestStageParseStepFigureRenderInput",
    "IngestStageParseStepFigureRenderOutput",
]
