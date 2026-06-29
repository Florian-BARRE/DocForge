# ====== Code Summary ======
# ConvertStep — the second ingest step. It derives the canonical PDF view from the original: native
# PDFs pass through unchanged, office formats are routed through the Gotenberg converter brick, and
# unknown formats fall back to a best-effort PDF passthrough. It counts the PDF pages and uploads
# the derived PDF to the object store at ``derived/{source_hash}/pdf``, threading the PDF bytes,
# key, and page count onto the shared IngestScratch for the probe step.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.bricks.providers.converter import (
    GOTENBERG_FORMATS,
    NATIVE_PDF_FORMATS,
)
from common_libs.pipeline.ingest.stages.base.step import IngestStep
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..helpers import IngestHelpers
from ..scratch import INGEST_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.providers.converter import GotenbergConverter
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.storage.s3.client import S3Client


class ConvertStep(IngestStep):
    """
    Native ingest step — derives the canonical PDF view and uploads it to the object store.

    Reads ``original_bytes``/``filename`` + the ingest scratch (original format, source hash);
    fills the scratch with the derived ``pdf_bytes``, ``pdf_key``, and ``page_count``.
    """

    KEY: ClassVar[str] = "convert"
    NAME: ClassVar[str] = "Convert"
    DESCRIPTION: ClassVar[str] = (
        "Derive the canonical PDF (native passthrough or office→PDF via Gotenberg), count its "
        "pages, and upload it to the object store."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("original_bytes", "filename", INGEST_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = (INGEST_SCRATCH_KEY,)

    def __init__(self, s3: "S3Client", converter: "GotenbergConverter") -> None:
        """
        Wire the step around the object-store client and the converter brick.

        Args:
            s3 (S3Client): SeaweedFS S3-compatible client for the derived PDF upload.
            converter (GotenbergConverter): Gotenberg client for office → PDF conversion.
        """
        IngestStep.__init__(self)
        self._s3 = s3
        self._converter = converter

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Derive the PDF, count its pages, upload it, and update the ingest scratch.

        Args:
            ctx (PipelineContext): The mutable run accumulator.

        Raises:
            Exception: Re-raises a conversion or upload failure (the stage is FAIL_DOC).
        """
        # 1. Read the scratch seeded by the content-address step.
        scratch = ctx.aux[INGEST_SCRATCH_KEY]
        original_format = scratch.original_format

        # 2. Obtain the PDF bytes + page count via the format fork (parity with the legacy S0).
        pdf_bytes, page_count = await self._derive_pdf(ctx.original_bytes, ctx.filename, original_format)

        # 3. Upload the derived PDF — a failure must fail the document, so log + re-raise.
        pdf_key = S3Helpers.key_pdf(scratch.source_hash)
        try:
            await self._s3.upload(key=pdf_key, data=pdf_bytes, content_type="application/pdf")
        except Exception as exc:
            self.logger.error(f"Derived-PDF upload failed for {pdf_key!r}: {exc}")
            raise
        self.logger.debug(f"Uploaded PDF → {pdf_key} ({page_count} pages)")

        # 4. Thread the derived artefacts onto the scratch for the probe step.
        scratch.pdf_bytes = pdf_bytes
        scratch.pdf_key = pdf_key
        scratch.page_count = page_count

    async def _derive_pdf(self, original_bytes: bytes, filename: str, original_format: str) -> tuple[bytes, int]:
        """
        Resolve the derived PDF bytes + page count for the given original format.

        Native PDFs pass through; office formats route through Gotenberg; unknown formats fall back
        to a best-effort PDF passthrough (a degraded path, logged but never silent).

        Args:
            original_bytes (bytes): Raw original file bytes.
            filename (str): Original filename (drives the Gotenberg conversion path).
            original_format (str): Lowercase original extension (no dot).

        Returns:
            tuple[bytes, int]: The derived PDF bytes and its page count.

        Raises:
            Exception: Re-raises a Gotenberg conversion failure (the stage is FAIL_DOC).
        """
        # 1. Native PDF — pass the bytes straight through.
        if original_format in NATIVE_PDF_FORMATS:
            return original_bytes, IngestHelpers.count_pages_fast(original_bytes)

        # 2. Office format — route through the Gotenberg converter brick.
        if original_format in GOTENBERG_FORMATS:
            try:
                convert_result = await self._converter.convert(original_bytes, filename)
            except Exception as exc:
                self.logger.error(f"Gotenberg conversion failed for {filename!r}: {exc}")
                raise
            return convert_result.pdf_bytes, convert_result.page_count

        # 3. Unknown format — degraded best-effort PDF passthrough (fallback coverage is later work).
        self.logger.warning(
            f"Unknown format {original_format!r} — attempting direct PDF passthrough."
        )
        return original_bytes, IngestHelpers.count_pages_fast(original_bytes)


__all__ = ["ConvertStep"]
