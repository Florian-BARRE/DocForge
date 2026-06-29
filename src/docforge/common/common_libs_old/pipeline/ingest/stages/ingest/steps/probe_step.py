# ====== Code Summary ======
# ProbeStep — the final ingest step. It performs the native/raster fork (PyMuPDF text-layer probe →
# ``needs_ocr``), builds the file-intrinsic implicit metadata, and assembles the durable
# IngestResult from the fully-populated IngestScratch, writing it onto the context for parse. This
# is the step that emits the ingest stage's output contract.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..helpers import IngestHelpers
from ..result import IngestResult
from ..scratch import INGEST_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext


class ProbeStep(IngestStep):
    """
    Native ingest step — detects the OCR fork and assembles the durable IngestResult.

    Reads ``original_bytes``/``filename`` + the fully-populated ingest scratch; writes
    ``ingest_result`` (the ingest stage's output contract consumed by parse).
    """

    KEY: ClassVar[str] = "probe"
    NAME: ClassVar[str] = "Probe & finalize"
    DESCRIPTION: ClassVar[str] = (
        "Detect the native/raster OCR fork, build the file-intrinsic implicit metadata, and "
        "assemble the ingest result."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("original_bytes", "filename", INGEST_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ingest_result",)

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Probe the derived PDF for raster pages, build implicit metadata, and emit the IngestResult.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Read the scratch populated by the content-address + convert steps.
        scratch = ctx.aux[INGEST_SCRATCH_KEY]

        # 2. Native / raster fork: detect whether any page lacks a text layer (→ OCR in enrich).
        needs_ocr = IngestHelpers.detect_raster_pages(scratch.pdf_bytes)
        if needs_ocr:
            self.logger.info(f"Raster pages detected in {ctx.filename!r} → OCR will be needed (enrich).")

        # 3. Build the file-intrinsic implicit metadata from the resolved values.
        file_size = len(ctx.original_bytes)
        implicit_meta = IngestHelpers.build_implicit_meta(
            filename=ctx.filename,
            original_format=scratch.original_format,
            file_size=file_size,
            source_hash=scratch.source_hash,
            page_count=scratch.page_count,
            needs_ocr=needs_ocr,
        )

        # 4. Assemble + emit the durable ingest result (the output contract consumed by parse).
        ctx.ingest_result = IngestResult(
            doc_id=scratch.doc_id,
            source_hash=scratch.source_hash,
            original_key=scratch.original_key,
            pdf_bytes=scratch.pdf_bytes,
            pdf_key=scratch.pdf_key,
            page_count=scratch.page_count,
            original_filename=ctx.filename,
            original_format=scratch.original_format,
            file_size=file_size,
            needs_ocr=needs_ocr,
            implicit_meta=implicit_meta,
        )
        self.logger.info(
            f"Ingest done: doc_id={scratch.doc_id} pages={scratch.page_count} needs_ocr={needs_ocr}"
        )


__all__ = ["ProbeStep"]
