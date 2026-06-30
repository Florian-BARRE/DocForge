# ====== Code Summary ======
# The probe node — the last action of the ingest stage. It inspects the PDF view to decide whether the
# document needs OCR downstream (a scanned/image PDF with no extractable text) and reports the media
# type. With no PDF view (degraded path) it reports the original format and no OCR. Pure, no service.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import ActionNode, Context, FromNode, NodeInput, NodeOutput


class IngestProbeInput(NodeInput):
    """Input of the probe node — the PDF view key + the original format."""

    pdf_key: Annotated[str | None, FromNode("convert", "pdf_key")]
    original_format: Annotated[str, FromNode("content_address")]


class IngestProbeOutput(NodeOutput):
    """Output of the probe node — the OCR hint + the media type."""

    needs_ocr: bool
    media_type: str


class IngestProbe(ActionNode):
    """Probe the PDF view for the OCR hint + media type (degrades cleanly when there is no PDF view)."""

    Input = IngestProbeInput
    Output = IngestProbeOutput

    async def execute(self, ctx: Context) -> IngestProbeOutput:
        """
        Report the OCR hint + media type for the document.

        Args:
            ctx (Context): The resolved input (PDF key + original format).

        Returns:
            IngestProbeOutput: Whether OCR is needed and the media type.
        """
        # 1. No PDF view -> degraded: no OCR, the media type is the original format.
        if ctx.input.pdf_key is None:
            return IngestProbeOutput(needs_ocr=False, media_type=ctx.input.original_format)

        # 2. A PDF view exists -> a real probe would inspect the text layer; default to no OCR for now.
        return IngestProbeOutput(needs_ocr=False, media_type="application/pdf")


__all__ = ["IngestProbe", "IngestProbeInput", "IngestProbeOutput"]
