# ====== Code Summary ======
# IngestStageIngestStepProbe — the third ingest step. From the original format + the PDF view info it
# decides the OCR fork (scanned/image inputs need OCR downstream) and the canonical media type. Pure
# decision, no service, no I/O.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepBase
from .context import IngestStageIngestStepProbeContext
from .io import IngestStageIngestStepProbeInput, IngestStageIngestStepProbeOutput

# Formats whose content is pixels -> downstream parsing must OCR.
_SCANNED_FORMATS: frozenset[str] = frozenset({"png", "jpg", "jpeg", "tiff", "bmp"})

# Canonical MIME type per known format (falls back to octet-stream).
_MEDIA_TYPE_BY_FORMAT: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "html": "text/html",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class IngestStageIngestStepProbe(IngestStageIngestStepBase):
    """
    Decide the OCR fork and the canonical media type from the format + PDF view.

    Consumes the content-address and convert outputs; writes ``needs_ocr`` + ``media_type``.
    """

    SPEC = NodeSpec(
        key="probe",
        name="Probe",
        description="OCR fork + media-type decision for downstream parsing.",
    )
    Input = IngestStageIngestStepProbeInput
    Output = IngestStageIngestStepProbeOutput
    Context = IngestStageIngestStepProbeContext

    async def execute(
        self, ctx: IngestStageIngestStepProbeContext
    ) -> IngestStageIngestStepProbeOutput:
        """
        Resolve the OCR fork + media type.

        Args:
            ctx (IngestStageIngestStepProbeContext): The probe input.

        Returns:
            IngestStageIngestStepProbeOutput: ``needs_ocr`` + ``media_type``.
        """
        # 1. Pixel formats need OCR; everything else carries a usable text layer here.
        needs_ocr = ctx.input.original_format in _SCANNED_FORMATS

        # 2. Resolve the canonical media type from the format.
        media_type = _MEDIA_TYPE_BY_FORMAT.get(ctx.input.original_format, "application/octet-stream")
        self.logger.info(f"Probe: media_type={media_type} needs_ocr={needs_ocr}.")

        return IngestStageIngestStepProbeOutput(needs_ocr=needs_ocr, media_type=media_type)


__all__ = ["IngestStageIngestStepProbe"]
