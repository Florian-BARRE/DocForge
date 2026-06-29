# ====== Code Summary ======
# ClassifyStep — the first (always-present) enrich capability pass. It downloads every enrichable
# FIGURE crop, classifies it through the classifier chain (provider-call cached on the crop hash),
# and records each figure's kind + relevance + the single routing DECISION (decorative / OCR / VLM /
# chart-schema) onto a FigureWork in the EnrichScratch. It ticks the classifier call/hit counters and
# figures_processed, then commits the classified IR. Crops that fail to download are skipped exactly
# as the legacy per-figure path skipped them (the block passes through untouched, not counted).

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, ClassVar

# ====== Third-Party Library Imports ======
from common_libs.domain.ir.models import BlockType, FigureKind

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.bricks.chain import ChainHelpers
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..cache_runner import CacheRunner
from ..ir_writer import EnrichIRWriter
from ..routing import EnrichRouting
from ..scratch import ENRICH_SCRATCH_KEY, EnrichScratch, FigureWork

if TYPE_CHECKING:
    from common_libs.domain.ir.models import Block
    from common_libs.pipeline.bricks.chain import Chain
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.storage.s3.client import S3Client


class ClassifyStep(IngestStep):
    """
    Native enrich step — classifies every figure and records the per-figure routing decision.

    Reads ``ir``; seeds ``ctx.aux["enrich_scratch"]`` (one FigureWork per enrichable figure) and
    writes the classified ``ir`` + a current ``enrich_result``.
    """

    KEY: ClassVar[str] = "classify"
    NAME: ClassVar[str] = "Classify"
    DESCRIPTION: ClassVar[str] = (
        "Download and classify every figure crop, then record each figure's OCR/VLM/chart routing "
        "decision."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", ENRICH_SCRATCH_KEY, "enrich_result")

    def __init__(
        self,
        classifier_chain: "Chain[Any, Any]",
        s3: "S3Client",
        provider_cache: "ProviderCallCache",
        ocr_enabled: bool,
        vlm_enabled: bool,
        chart_to_data: bool,
    ) -> None:
        """
        Wire the step around the classifier chain + the routing inputs.

        Args:
            classifier_chain (Chain[Any, Any]): Ordered figure classifier chain (non-empty).
            s3 (S3Client): SeaweedFS client for figure crop downloads.
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            ocr_enabled (bool): Whether an OCR chain is wired (drives the routing decision).
            vlm_enabled (bool): Whether a VLM chain is wired (drives the routing decision).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag (drives the chart-schema decision).
        """
        IngestStep.__init__(self)
        self._classifier_chain = classifier_chain
        self._s3 = s3
        self._provider_cache = provider_cache
        self._ocr_enabled = ocr_enabled
        self._vlm_enabled = vlm_enabled
        self._chart_to_data = chart_to_data

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Classify each enrichable figure and seed the enrich scratch with the routing decisions.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        ir = ctx.ir
        self.logger.info(f"Enrich classify: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}")

        # 1. Fresh scratch for this run (one FigureWork per enrichable figure, in document order).
        scratch = EnrichScratch(language=ir.language)

        # 2. Classify each enrichable FIGURE block; non-figure / crop-less blocks are not scratch items.
        for block in ir.blocks:
            if block.type != BlockType.FIGURE or block.figure is None or not block.figure.crop_key:
                continue
            await self._classify_block(block, scratch)

        # 3. Stash the scratch + commit the classified IR (decorative figures are already final).
        ctx.aux[ENRICH_SCRATCH_KEY] = scratch
        EnrichIRWriter.commit(ctx, scratch)
        self.logger.info(
            f"Enrich classify done: doc_id={ir.doc_id} classified={len(scratch.figures)} "
            f"classifier(call/hit)={scratch.counters.classifier_calls}/"
            f"{scratch.counters.classifier_cache_hits}"
        )

    async def _classify_block(self, block: "Block", scratch: EnrichScratch) -> None:
        """
        Download + classify one figure block and record its FigureWork in the scratch.

        Args:
            block (Block): The FIGURE block to classify (has a non-empty crop_key).
            scratch (EnrichScratch): The per-run scratch to populate.
        """
        crop_key = block.figure.crop_key

        # 1. Download the crop. A failure skips the figure entirely (block untouched, not counted) —
        # the same behaviour as the legacy FigureEnricher download guard.
        try:
            crop_bytes = await self._s3.download(crop_key)
        except Exception as exc:
            self.logger.warning(
                f"Enrich: could not download crop for block={block.id}: {exc} — skipping"
            )
            return
        crop_hash = hashlib.sha256(crop_bytes).hexdigest()

        # 2. Classify (cached on the crop hash); a None classification falls back to PHOTO/0.0.
        classification, cls_trace, was_hit = await CacheRunner.run_classify(
            self._classifier_chain, self._provider_cache, crop_bytes, crop_hash,
        )
        if was_hit:
            scratch.counters.classifier_cache_hits += 1
        else:
            scratch.counters.classifier_calls += 1
        if classification is None:
            kind, relevance = FigureKind.PHOTO, 0.0
        else:
            kind, relevance = classification.kind, classification.confidence

        # 3. Resolve the routing decision once + record the work item (counted as processed).
        decision = EnrichRouting.decide(kind, self._ocr_enabled, self._vlm_enabled, self._chart_to_data)
        scratch.counters.figures_processed += 1
        scratch.figures[block.id] = FigureWork(
            block_id=block.id,
            crop_key=crop_key,
            crop_bytes=crop_bytes,
            crop_hash=crop_hash,
            kind=kind,
            relevance=relevance,
            decorative=decision.decorative,
            do_ocr=decision.do_ocr,
            do_vlm=decision.do_vlm,
            use_chart_schema=decision.use_chart_schema,
            base_traces=list(block.chain_traces),
            classify_trace=cls_trace,
        )

    def describe(self) -> StepSchema:
        """Emit a chain-kind schema (the classifier provider category + ordered provider choices)."""
        return StepSchema(
            kind="chain",
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            category="classify",
            providers=[ChainHelpers.default_provider_id(p) for p in self._classifier_chain.providers],
        )


__all__ = ["ClassifyStep"]
