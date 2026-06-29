# ====== Code Summary ======
# IngestStageIngestStepConvert — the second ingest step. It derives a PDF view of the original:
# office/HTML formats are converted via the stage-local converter and uploaded; an original that is
# already a PDF is passed through (its original key is reused); anything else yields no PDF. It
# consumes the content-address step's output and requires the object store + the converter.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepBase
from .context import IngestStageIngestStepConvertContext
from .errors import IngestStageIngestStepConvertError
from .io import IngestStageIngestStepConvertInput, IngestStageIngestStepConvertOutput

# Formats that must be converted to PDF before downstream parsing.
_OFFICE_FORMATS: frozenset[str] = frozenset({"docx", "pptx", "xlsx", "odt", "html"})


class IngestStageIngestStepConvert(IngestStageIngestStepBase):
    """
    Derive a PDF view of the original (convert office/HTML, pass through PDF, skip the rest).

    Consumes the content-address step's output; writes the PDF key and whether a conversion happened.
    """

    SPEC = NodeSpec(
        key="convert",
        name="Convert",
        description="Office/HTML -> PDF conversion (PDF passthrough; others skipped).",
    )
    Input = IngestStageIngestStepConvertInput
    Output = IngestStageIngestStepConvertOutput
    Context = IngestStageIngestStepConvertContext
    Error = IngestStageIngestStepConvertError
    REQUIRES = (
        ServiceRef(name="object_store", description="Content-addressed blob store."),
        ServiceRef(name="converter", description="Office/HTML -> PDF converter."),
    )

    async def execute(
        self, ctx: IngestStageIngestStepConvertContext
    ) -> IngestStageIngestStepConvertOutput:
        """
        Produce the PDF view according to the original format.

        Args:
            ctx (IngestStageIngestStepConvertContext): Typed input + object store + converter.

        Returns:
            IngestStageIngestStepConvertOutput: The PDF key (or None) and the conversion flag.

        Raises:
            IngestStageIngestStepConvertError: When conversion or the PDF upload fails.
        """
        fmt = ctx.input.original_format

        # 1. Already a PDF -> reuse the original as the PDF view (no conversion).
        if fmt == "pdf":
            self.logger.debug(f"Convert: {fmt!r} is already PDF — passthrough.")
            return IngestStageIngestStepConvertOutput(pdf_key=ctx.input.original_key, converted=False)

        # 2. Non-convertible format (e.g. plain text) -> no PDF view.
        if fmt not in _OFFICE_FORMATS:
            self.logger.debug(f"Convert: {fmt!r} has no PDF view.")
            return IngestStageIngestStepConvertOutput(pdf_key=None, converted=False)

        # 3. Office/HTML -> convert (real ConverterProvider) then upload the PDF under its key.
        pdf_key = f"pdf/{ctx.input.source_hash}.pdf"
        try:
            result = await ctx.converter.convert(ctx.input.original_bytes, ctx.input.filename)
            await ctx.object_store.upload(pdf_key, result.pdf_bytes, "application/pdf")
        except Exception as exc:
            self.logger.error(f"Conversion of {fmt!r} failed for {ctx.input.source_hash[:12]}…: {exc}")
            raise IngestStageIngestStepConvertError(
                f"Failed to convert {fmt!r} to PDF.",
                node_key=self.key,
                cause=exc,
            ) from exc

        self.logger.info(f"Convert: {fmt!r} -> PDF ({result.page_count}p) uploaded at {pdf_key}.")
        return IngestStageIngestStepConvertOutput(
            pdf_key=pdf_key, converted=True, page_count=result.page_count
        )


__all__ = ["IngestStageIngestStepConvert"]
