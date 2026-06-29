# ====== Code Summary ======
# OcrStep — the OCR enrich capability pass. It runs the OCR chain (provider-call cached on the crop
# hash + language) over EXACTLY the figures the classify step's routing marked ``do_ocr``, in document
# order, and records the extracted text + the OCR trace on each FigureWork. It ticks the OCR call/hit
# counters and commits the IR with the OCR text folded into the figure enrichments. It is only built
# when an OCR chain is wired (the routing never marks ``do_ocr`` otherwise).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.bricks.chain import ChainHelpers
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..cache_runner import CacheRunner
from ..ir_writer import EnrichIRWriter
from ..scratch import ENRICH_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.chain import Chain
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.pipeline.stages.context import PipelineContext


class OcrStep(IngestStep):
    """
    Native enrich step — OCRs the figures the routing marked for text extraction.

    Reads ``ir`` + ``ctx.aux["enrich_scratch"]``; writes each routed figure's OCR text onto its
    FigureWork and commits the updated ``ir`` + ``enrich_result``.
    """

    KEY: ClassVar[str] = "ocr"
    NAME: ClassVar[str] = "OCR"
    DESCRIPTION: ClassVar[str] = "Extract text from the text-bearing figures the routing selected."
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir", ENRICH_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", "enrich_result")

    def __init__(self, ocr_chain: "Chain[Any, Any]", provider_cache: "ProviderCallCache") -> None:
        """
        Wire the step around the OCR chain.

        Args:
            ocr_chain (Chain[Any, Any]): Ordered OCR chain (non-empty when this step is built).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
        """
        IngestStep.__init__(self)
        self._ocr_chain = ocr_chain
        self._provider_cache = provider_cache

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run OCR over the routed figures and fold the extracted text into the IR.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        scratch = ctx.aux[ENRICH_SCRATCH_KEY]

        # 1. OCR only the figures the routing marked, in document (insertion) order — preserving the
        # legacy provider-call cache hit/miss pattern across duplicate crops.
        for work in scratch.figures.values():
            if not work.do_ocr:
                continue
            ocr_result, ocr_trace, was_hit = await CacheRunner.run_ocr(
                self._ocr_chain, self._provider_cache, work.crop_bytes, work.crop_hash, scratch.language,
            )
            work.ocr_trace = ocr_trace
            if ocr_result is None:
                continue
            work.ocr_text = ocr_result.text if ocr_result.text.strip() else None
            if was_hit:
                scratch.counters.ocr_cache_hits += 1
            else:
                scratch.counters.ocr_calls += 1

        # 2. Commit the IR with the OCR text folded in.
        EnrichIRWriter.commit(ctx, scratch)

    def describe(self) -> StepSchema:
        """Emit a chain-kind schema (the OCR provider category + ordered provider choices)."""
        return StepSchema(
            kind="chain",
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            category="ocr",
            providers=[ChainHelpers.default_provider_id(p) for p in self._ocr_chain.providers],
        )


__all__ = ["OcrStep"]
