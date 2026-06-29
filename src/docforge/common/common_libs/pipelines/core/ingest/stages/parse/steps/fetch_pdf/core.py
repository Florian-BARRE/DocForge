# ====== Code Summary ======
# IngestStageParseStepFetchPdf — the first parse step. It downloads the PDF view bytes from the object
# store under the ingest-provided ``pdf_key`` so the parse step can drive the parser chain over them.
# When there is no PDF view (``pdf_key`` is None — a non-convertible original) it returns no bytes,
# and the parse step degrades to an empty IR. It declares the object store as its only required
# service.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ..base import IngestStageParseStepBase
from .context import IngestStageParseStepFetchPdfContext
from .errors import IngestStageParseStepFetchPdfError
from .io import IngestStageParseStepFetchPdfInput, IngestStageParseStepFetchPdfOutput


class IngestStageParseStepFetchPdf(IngestStageParseStepBase):
    """
    Download the PDF view bytes from the object store (or none when there is no PDF view).

    Reads the ``pdf_key`` from its parent stage input; writes the raw PDF bytes for the parse step.
    """

    SPEC = NodeSpec(
        key="fetch_pdf",
        name="Fetch PDF",
        description="Download the PDF view bytes from the object store (None when there is no PDF).",
    )
    Input = IngestStageParseStepFetchPdfInput
    Output = IngestStageParseStepFetchPdfOutput
    Context = IngestStageParseStepFetchPdfContext
    Error = IngestStageParseStepFetchPdfError
    REQUIRES = (ServiceRef(name="object_store", description="Content-addressed blob store."),)

    async def execute(
        self, ctx: IngestStageParseStepFetchPdfContext
    ) -> IngestStageParseStepFetchPdfOutput:
        """
        Download the PDF view bytes, or return none when there is no PDF view.

        Args:
            ctx (IngestStageParseStepFetchPdfContext): Typed input + the object store.

        Returns:
            IngestStageParseStepFetchPdfOutput: The PDF bytes, or None when there was no PDF view.

        Raises:
            IngestStageParseStepFetchPdfError: When the PDF view download fails.
        """
        # 1. No PDF view -> nothing to fetch; the parse step degrades to an empty IR.
        pdf_key = ctx.input.pdf_key
        if pdf_key is None:
            self.logger.info(f"Fetch PDF: no PDF view (pdf_key is None) - degraded parse downstream.")
            return IngestStageParseStepFetchPdfOutput(pdf_bytes=None)

        # 2. Download the PDF view bytes — a failure must surface as this step's typed error.
        try:
            pdf_bytes = await ctx.object_store.download(pdf_key)
        except Exception as exc:
            self.logger.error(f"PDF view download failed for {pdf_key!r}: {exc}")
            raise IngestStageParseStepFetchPdfError(
                f"Failed to download PDF view {pdf_key!r}.",
                node_key=self.key,
                cause=exc,
            ) from exc

        self.logger.info(f"Fetch PDF: downloaded {len(pdf_bytes)} bytes from {pdf_key!r}.")
        return IngestStageParseStepFetchPdfOutput(pdf_bytes=pdf_bytes)


__all__ = ["IngestStageParseStepFetchPdf"]
