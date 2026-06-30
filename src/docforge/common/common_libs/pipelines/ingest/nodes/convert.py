# ====== Code Summary ======
# The convert node — turns the original into the canonical PDF view the parser works on. A native PDF
# is stored as-is; an office/HTML document is converted via the injected converter service (Gotenberg);
# anything else (e.g. plain text) has no PDF view and flows on degraded (pdf_key=None) so the parser
# can still produce an empty IR. The converter is an INFRA service (one deployment URL from
# RUNTIME_CONFIG, injected at bootstrap) — never a hardcoded endpoint in this node.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromNode,
    FromRunInput,
    NodeInput,
    NodeOutput,
)
from common_libs.storage.s3.helpers import S3Helpers

# Formats that already are / can become a PDF view.
_NATIVE_PDF = frozenset({"pdf"})
_CONVERTIBLE = frozenset({"docx", "doc", "pptx", "ppt", "xlsx", "xls", "odt", "odp", "ods", "html", "htm", "rtf"})


class IngestConvertInput(NodeInput):
    """Input of the convert node — the addressed original + its bytes."""

    source_hash: Annotated[str, FromNode("content_address")]
    original_format: Annotated[str, FromNode("content_address")]
    original_bytes: Annotated[bytes, FromRunInput()]
    filename: Annotated[str, FromRunInput()]


class IngestConvertOutput(NodeOutput):
    """Output of the convert node — the PDF view key (None when there is no PDF view) + conversion meta."""

    pdf_key: str | None
    converted: bool
    page_count: int | None


class IngestConvert(ActionNode):
    """Produce the canonical PDF view: store native PDFs, convert office/HTML, pass others through."""

    Input = IngestConvertInput
    Output = IngestConvertOutput

    async def execute(self, ctx: Context) -> IngestConvertOutput:
        """
        Produce the PDF view of the original (native / converted / none).

        Args:
            ctx (Context): The resolved input + the object store and converter services.

        Returns:
            IngestConvertOutput: The PDF key (or None when no PDF view), conversion flag, page count.
        """
        fmt = ctx.input.original_format
        store = ctx.service("object_store")
        pdf_key = S3Helpers.key_pdf(ctx.input.source_hash)

        # 1. Native PDF — store the bytes as the PDF view, no conversion.
        if fmt in _NATIVE_PDF:
            await store.upload(pdf_key, ctx.input.original_bytes)
            return IngestConvertOutput(pdf_key=pdf_key, converted=False, page_count=None)

        # 2. Convertible document — convert via the converter service, store the produced PDF.
        if fmt in _CONVERTIBLE:
            result = await ctx.service("converter").convert(ctx.input.original_bytes, ctx.input.filename)
            await store.upload(pdf_key, result.pdf_bytes)
            self.logger.info(f"Converted {fmt!r} -> PDF ({result.page_count} pages).")
            return IngestConvertOutput(pdf_key=pdf_key, converted=True, page_count=result.page_count)

        # 3. No PDF view (e.g. plain text) — flow on degraded; the parser produces an empty IR.
        self.logger.info(f"No PDF view for format {fmt!r}; flowing on degraded.")
        return IngestConvertOutput(pdf_key=None, converted=False, page_count=None)


__all__ = ["IngestConvert", "IngestConvertInput", "IngestConvertOutput"]
