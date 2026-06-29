# ====== Code Summary ======
# S1 — Parse stage: Docling-or-chain → DocumentIR + figure crops → SeaweedFS.
# S1 operates on the PDF produced by S0 and never touches the original file again.
# The parser is delivered as a Chain[ParserProvider, DocumentIR] so the stage can
# escalate to a fallback parser (MinerU/Marker — Phase B) when the first provider's
# quality_score falls below the configured gate.
#
# Figure-crop rendering + markdown serialization/upload live in S1Renderer (s1_renderer.py).
# Pure IR transformations (chain-trace stamping, figure crop key patching) live in
# s1_helpers.py (S1Helpers).  This class only drives the parser chain and orchestrates them.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
    from common_libs.storage.s3.client import S3Client

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from common_libs.pipeline.bricks.chain import Chain

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR

# ====== Local Project Imports ======
from .helpers import S1Helpers
from .renderer import S1Renderer
from .result import S1Result


class S1ParseStage(LoggerClass):
    """
    S1 — Parsing and rasterization stage backed by a parser chain.

    Responsibilities:
      1. Invoke the parser chain; the first provider whose IR passes the gate wins.
      2. Persist the full attempt log on ``DocumentIR.chain_traces`` for lineage.
      3. Render each FIGURE bbox and upload the crop to SeaweedFS (via S1Renderer).
      4. Serialise the IR to markdown and upload it to SeaweedFS (via S1Renderer).

    What S1 does NOT do:
      - No OCR, no VLM, no classification (S2 territory).
      - No chunking, no embedding (S4–S6).
      - No Postgres writes (handled by the engine).

    Helper split rationale:
      Pure IR transformations are delegated to ``S1Helpers``; figure-crop rendering and
      markdown upload (which carry self.logger calls) are delegated to ``S1Renderer``.
    """

    def __init__(self, parse_chain: Chain[Any, Any], s3: S3Client) -> None:
        """
        Initialise S1 with its dependencies.

        Args:
            parse_chain (Chain[ParserProvider, DocumentIR]): Ordered parser chain.
            s3 (S3Client): SeaweedFS client for blob uploads.
        """
        LoggerClass.__init__(self)
        self._parse_chain = parse_chain
        self._renderer = S1Renderer(s3)

    @property
    def parse_chain(self) -> Chain[Any, Any]:
        """Expose the chain so the engine can fingerprint its signature."""
        return self._parse_chain

    async def run(self, s0: IngestResult, fingerprint: str | None = None) -> S1Result:
        """
        Execute the S1 parse stage.

        Args:
            s0 (IngestResult): Output from the ingest stage (PDF bytes must be set).
            fingerprint (str | None): P2 stage fingerprint used for the markdown S3 key.

        Returns:
            S1Result: The parsed IR (with chain trace), markdown key, and crop keys.

        Raises:
            ChainExhaustedError: When every parser escalates/raises AND the parse gate's
                ``failure_policy="raise"`` (the default). The chain itself raises with a
                precise per-provider reason; the worker fail-closed boundary marks the doc
                ``failed``. A collection that sets ``failure_policy="continue"`` instead
                yields a degraded (result=None) outcome — handled below.
        """
        self.logger.info(
            f"S1 started: doc_id={s0.doc_id} pages={s0.page_count}"
        )

        # 1. Run the parser chain.  Each provider produces a full DocumentIR; the chain
        # stops at the first one whose quality_score passes the gate. On exhaustion the
        # chain applies its failure policy itself (raise → ChainExhaustedError propagates;
        # continue → degraded outcome with result=None handled below).
        outcome = await self._parse_chain.call(
            lambda p: p.parse(
                pdf_bytes=s0.pdf_bytes,
                doc_id=s0.doc_id,
                source_hash=s0.source_hash,
            )
        )
        if outcome.result is None:
            # Reached only under failure_policy="continue": the expert chose to let a doc
            # proceed without a parse. There is no IR to render — return an empty IR so the
            # document ends "done" with no blocks (the expert's explicit call, see design §11bis Q3).
            self.logger.warning(
                f"S1 parse chain degraded for doc_id={s0.doc_id} "
                f"({len(outcome.attempts)} provider(s) attempted, none produced an IR) — "
                f"continuing with an empty IR per the gate's failure_policy=continue."
            )
            empty_ir = S1Helpers.empty_ir(s0)
            empty_ir = S1Helpers.stamp_parse_trace(empty_ir, outcome)
            return S1Result(ir=empty_ir, markdown_key=None, figure_crop_keys={})

        ir: DocumentIR = outcome.result

        # 2. Stamp the parse trace on the IR so every downstream consumer sees the lineage.
        ir = S1Helpers.stamp_parse_trace(ir, outcome)

        # 3. Render and upload figure crops (page screenshots are generated on the fly).
        figure_crop_keys = await self._renderer.render_and_upload(s0, ir)

        # 4. Patch figure blocks with their crop_key.
        ir = S1Helpers.patch_figure_crop_keys(ir, figure_crop_keys)

        # 5. Serialise IR → markdown → upload.
        markdown_key = await self._renderer.upload_markdown(s0, ir, fingerprint=fingerprint)

        result = S1Result(
            ir=ir,
            markdown_key=markdown_key,
            figure_crop_keys=figure_crop_keys,
        )

        self.logger.info(
            f"S1 done: doc_id={s0.doc_id} "
            f"blocks={len(ir.blocks)} figures={len(figure_crop_keys)} "
            f"final_parser={outcome.final_provider} attempts={len(outcome.attempts)}"
        )
        return result
