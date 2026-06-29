# ====== Code Summary ======
# MarkdownStep — the final parse step. It serialises the canonical IR to faithful markdown and
# uploads it to the object store under a fingerprint-derived key, then assembles the durable
# ParseResult (the parse stage's output contract consumed by enrich + the worker node-cache codec).
# A degraded (no-parse) run skips serialisation entirely (markdown_key=None), exactly like the legacy
# path. The markdown key is derived from THIS node's (parse) fingerprint — the same value that keyed
# the legacy markdown blob — read from ``ctx.fingerprints["parse"]``.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.domain.ir.serializer import MarkdownSerializer
from common_libs.pipeline.ingest.stages.base.step import IngestStep
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..result import ParseResult
from ..scratch import PARSE_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.storage.s3.client import S3Client

# Fallback markdown-key fingerprint when the parse node fingerprint is absent (tests / dry runs).
# Kept byte-identical to the legacy default so a fingerprint-less markdown key never changes.
_NO_FINGERPRINT = "s1_no_fingerprint"


class MarkdownStep(IngestStep):
    """
    Native parse step — serialises the IR to markdown, uploads it, and emits the ParseResult.

    Reads ``ir``, ``ingest_result`` (source hash), and the parse scratch (degraded flag + figure
    crop keys); writes ``parse_result`` (the parse stage's output contract consumed by enrich).
    """

    KEY: ClassVar[str] = "markdown"
    NAME: ClassVar[str] = "Render markdown"
    DESCRIPTION: ClassVar[str] = (
        "Serialise the canonical IR to faithful markdown, upload it to the object store under the "
        "parse fingerprint, and assemble the parse result."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir", "ingest_result", PARSE_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("parse_result",)

    def __init__(self, s3: "S3Client") -> None:
        """
        Wire the step around the object-store client + the markdown serialiser.

        Args:
            s3 (S3Client): SeaweedFS S3-compatible client for the markdown upload.
        """
        IngestStep.__init__(self)
        self._s3 = s3
        self._md_serializer = MarkdownSerializer()

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Serialise + upload the markdown view and assemble the durable ParseResult.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Read the canonical IR + the cross-step scratch (degraded flag + figure crop keys).
        ir = ctx.ir
        scratch = ctx.aux[PARSE_SCRATCH_KEY]

        # 2. Degraded (no-parse) outcome: there is no IR to serialise — emit markdown_key=None,
        # exactly like the legacy path (the document ends "done" with no markdown view).
        if scratch.degraded:
            ctx.parse_result = ParseResult(ir=ir, markdown_key=None, figure_crop_keys={})
            self.logger.info(f"Parse done (degraded, no markdown): doc_id={ctx.ingest_result.doc_id}")
            return

        # 3. Serialise the IR → markdown and upload under the parse-node fingerprint key. The
        # fingerprint is THIS node's ("parse"); the caching middleware populates it before the stage
        # runs and it keys the markdown blob (legacy run_s1 passed s1_fp for exactly this reason).
        markdown_text = self._md_serializer.serialize(ir)
        fingerprint = ctx.fingerprints.get(self.KEY_PARSE_NODE) or _NO_FINGERPRINT
        markdown_key = S3Helpers.key_markdown(ctx.ingest_result.source_hash, fingerprint)
        await self._s3.upload(
            key=markdown_key,
            data=markdown_text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        self.logger.debug(f"Uploaded markdown -> {markdown_key}")

        # 4. Assemble + emit the durable parse result (the output contract consumed by enrich).
        ctx.parse_result = ParseResult(
            ir=ir,
            markdown_key=markdown_key,
            figure_crop_keys=scratch.figure_crop_keys,
        )
        self.logger.info(
            f"Parse done: doc_id={ctx.ingest_result.doc_id} blocks={len(ir.blocks)} "
            f"figures={len(scratch.figure_crop_keys)}"
        )

    # The markdown blob is keyed by the parse STAGE node fingerprint (StageKey.PARSE == "parse"),
    # not this step's KEY ("markdown") — the engine writes ctx.fingerprints["parse"] before the run.
    KEY_PARSE_NODE: ClassVar[str] = "parse"


__all__ = ["MarkdownStep"]
