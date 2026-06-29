# ====== Code Summary ======
# IO contract for the probe step: it reads the original format (from content-address) and the PDF
# view info (from convert), and decides the OCR fork + the canonical media type. Pure decision — it
# requires no service.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput


class IngestStageIngestStepProbeInput(NodeInput):
    """
    Input of the probe step.

    Attributes:
        original_format (str): Original format (from the content-address step).
        pdf_key (str | None): PDF view key (from the convert step), or None when there is no PDF.
    """

    original_format: Annotated[
        str, FromSibling(producer="content_address", field="original_format")
    ]
    pdf_key: Annotated[str | None, FromSibling(producer="convert", field="pdf_key", required=False)]


class IngestStageIngestStepProbeOutput(NodeOutput):
    """
    Output of the probe step.

    Attributes:
        needs_ocr (bool): True when downstream parsing must OCR (scanned/image input).
        media_type (str): The canonical MIME type of the document.
    """

    needs_ocr: bool
    media_type: str


__all__ = [
    "IngestStageIngestStepProbeInput",
    "IngestStageIngestStepProbeOutput",
]
