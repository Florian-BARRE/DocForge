# ====== Code Summary ======
# VlmStep — the VLM enrich capability pass. It runs the VLM chain (provider-call cached on the crop
# hash + grounding/chart-schema params) over EXACTLY the figures the classify step's routing marked
# ``do_vlm``, in document order, grounding each call on the OCR text recorded by the OCR step. It
# records the VLM description + the raw structured output (which the chart step later mines for a data
# table) + the VLM trace on each FigureWork, ticks the VLM call/hit counters, and commits the IR. The
# chart-to-data decision (``use_chart_schema``) was taken at classify time and is a parameter of THIS
# single VLM call — never a second provider call — so the cache key matches the legacy path exactly.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.bricks.chain import ChainHelpers
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..ir_writer import EnrichIRWriter
from ..scratch import ENRICH_SCRATCH_KEY
from ..vlm_runner import VlmRunner

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.chain import Chain
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.pipeline.stages.context import PipelineContext


class VlmStep(IngestStep):
    """
    Native enrich step — VLM-describes the figures the routing marked for a visual description.

    Reads ``ir`` + ``ctx.aux["enrich_scratch"]``; writes each routed figure's description + raw
    structured output onto its FigureWork and commits the updated ``ir`` + ``enrich_result``.
    """

    KEY: ClassVar[str] = "vlm"
    NAME: ClassVar[str] = "VLM"
    DESCRIPTION: ClassVar[str] = (
        "Describe the figures the routing selected via a vision-language model, grounded on the OCR "
        "text."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir", ENRICH_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", "enrich_result")

    def __init__(self, vlm_chain: "Chain[Any, Any]", provider_cache: "ProviderCallCache") -> None:
        """
        Wire the step around the VLM chain.

        Args:
            vlm_chain (Chain[Any, Any]): Ordered VLM chain (non-empty when this step is built).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
        """
        IngestStep.__init__(self)
        self._vlm_chain = vlm_chain
        self._provider_cache = provider_cache

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the VLM over the routed figures and fold the descriptions into the IR.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        scratch = ctx.aux[ENRICH_SCRATCH_KEY]

        # 1. VLM only the figures the routing marked, in document (insertion) order; ground each call
        # on the figure's OCR text and request the chart schema iff the routing decided so.
        for work in scratch.figures.values():
            if not work.do_vlm:
                continue
            vlm_result, vlm_trace, was_hit = await VlmRunner.run_vlm(
                self._vlm_chain, self._provider_cache, work.crop_bytes, work.crop_hash,
                work.ocr_text, work.use_chart_schema,
            )
            work.vlm_trace = vlm_trace
            if vlm_result is None:
                continue
            work.description = vlm_result.description or None
            work.vlm_structured = vlm_result.structured
            if was_hit:
                scratch.counters.vlm_cache_hits += 1
            else:
                scratch.counters.vlm_calls += 1

        # 2. Commit the IR with the VLM descriptions folded in (the chart step mines vlm_structured).
        EnrichIRWriter.commit(ctx, scratch)

    def describe(self) -> StepSchema:
        """Emit a chain-kind schema (the VLM provider category + ordered provider choices)."""
        return StepSchema(
            kind="chain",
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            category="vlm",
            providers=[ChainHelpers.default_provider_id(p) for p in self._vlm_chain.providers],
        )


__all__ = ["VlmStep"]
