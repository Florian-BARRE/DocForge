# ====== Code Summary ======
# IngestDocStep — the single native step of the ingest (S0) stage. It reads the run inputs
# (file bytes, filename, doc id) from the context, delegates to the existing S0IngestStage
# (content-address + office->PDF conversion + OCR-fork detection + object-store upload), and writes
# the S0Result + the content-address source_hash back. Named IngestDocStep (not IngestStep) to
# avoid colliding with the ingest-family step base ``IngestStep``.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage


class IngestDocStep(IngestStep):
    """
    Native ingest step — delegates to the legacy S0 ingestion logic, threading IO via the context.

    Reads ``file_bytes``/``filename``/``doc_id``; writes ``s0_result`` and ``source_hash``.
    """

    KEY: ClassVar[str] = "ingest"
    NAME: ClassVar[str] = "Ingest"
    DESCRIPTION: ClassVar[str] = (
        "Content-address the original, convert office formats to PDF, detect the OCR fork, "
        "and upload artifacts to the object store."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("file_bytes", "filename", "doc_id")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s0_result", "source_hash")

    def __init__(self, ingestor: "S0IngestStage") -> None:
        """
        Wire the step around the ingestion implementation.

        Args:
            ingestor (S0IngestStage): The ingestion implementation (converter + object store).
        """
        IngestStep.__init__(self)
        self._ingestor = ingestor

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the ingestion implementation and write its output onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Thread doc_id verbatim: the document row is pre-created in Postgres, so a None here
        # would make S0 mint a fresh id and orphan that row.
        doc_id = str(ctx.doc_id) if ctx.doc_id is not None else None
        result = await self._ingestor.run(ctx.file_bytes, ctx.filename, doc_id)

        # 2. Write the declared PRODUCES back onto the context.
        ctx.s0_result = result
        ctx.source_hash = result.source_hash


__all__ = ["IngestDocStep"]
