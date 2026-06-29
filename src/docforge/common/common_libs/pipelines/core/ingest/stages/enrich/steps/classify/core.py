# ====== Code Summary ======
# IngestStageEnrichStepClassify - the first (always-present) enrich capability pass. It downloads
# every enrichable FIGURE crop, classifies it through the classifier chain (provider-call cached on
# the crop sha256), and records each figure's kind + relevance + the single routing DECISION
# (decorative / OCR / VLM / chart-schema) onto a FigureWork. It returns the classified IR plus the
# seeded work list (threaded to the OCR / VLM / chart steps) and the classifier counters. Crops that
# fail to download are skipped exactly as the legacy per-figure path skipped them.

# ====== Standard Library Imports ======
import hashlib

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import Block, BlockType, FigureKind
from common_libs.pipelines import ChainRef, NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ...cache_runner import CacheRunner
from ...figure_work import FigureWork
from ...ir_builder import EnrichIRWriter
from ...routing import EnrichRouting
from ..base import IngestStageEnrichStepBase
from .context import IngestStageEnrichStepClassifyContext
from .errors import IngestStageEnrichStepClassifyError
from .io import IngestStageEnrichStepClassifyInput, IngestStageEnrichStepClassifyOutput


class IngestStageEnrichStepClassify(IngestStageEnrichStepBase):
    """
    Classify every figure and record the per-figure routing decision.

    Reads ``ir``; downloads + classifies each enrichable figure crop, seeds one FigureWork per
    figure, and returns the classified IR + the work list (with classifier counters).
    """

    SPEC = NodeSpec(
        key="classify",
        name="Classify",
        description=(
            "Download and classify every figure crop, then record each figure's OCR/VLM/chart "
            "routing decision."
        ),
    )
    Input = IngestStageEnrichStepClassifyInput
    Output = IngestStageEnrichStepClassifyOutput
    Context = IngestStageEnrichStepClassifyContext
    Error = IngestStageEnrichStepClassifyError
    REQUIRES = (
        ChainRef(name="classifier_chain", category="classifier", description="Ordered figure classifier chain."),
        ServiceRef(name="object_store", description="Content-addressed blob store (crop downloads)."),
        ServiceRef(name="provider_cache", description="Cross-document provider-call cache."),
    )

    def __init__(self, ocr_enabled: bool, vlm_enabled: bool, chart_to_data: bool) -> None:
        """
        Wire the step around the routing inputs (which capabilities are active).

        Args:
            ocr_enabled (bool): Whether an OCR chain is wired (drives the routing decision).
            vlm_enabled (bool): Whether a VLM chain is wired (drives the routing decision).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag (drives the chart-schema decision).
        """
        super().__init__()
        self._ocr_enabled = ocr_enabled
        self._vlm_enabled = vlm_enabled
        self._chart_to_data = chart_to_data

    async def execute(
        self, ctx: IngestStageEnrichStepClassifyContext
    ) -> IngestStageEnrichStepClassifyOutput:
        """
        Classify each enrichable figure and seed the work list with the routing decisions.

        Args:
            ctx (IngestStageEnrichStepClassifyContext): Typed input + classifier chain + store + cache.

        Returns:
            IngestStageEnrichStepClassifyOutput: The classified IR + seeded work list + counters.
        """
        ir = ctx.input.ir
        self.logger.info(f"Enrich classify: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}")

        # 1. Classify each enrichable FIGURE block; non-figure / crop-less blocks are not work items.
        works: list[FigureWork] = []
        calls = hits = 0
        for block in ir.blocks:
            if block.type != BlockType.FIGURE or block.figure is None or not block.figure.crop_key:
                continue
            work, was_hit = await self._classify_block(ctx, block)
            if work is None:
                continue
            works.append(work)
            hits, calls = (hits + 1, calls) if was_hit else (hits, calls + 1)

        # 2. Rebuild the IR with the classified figures (decorative figures are already final).
        classified_ir = EnrichIRWriter.apply(ir, works)
        self.logger.info(
            f"Enrich classify done: doc_id={ir.doc_id} classified={len(works)} "
            f"classifier(call/hit)={calls}/{hits}"
        )
        return IngestStageEnrichStepClassifyOutput(
            ir=classified_ir,
            figure_works=works,
            classifier_calls=calls,
            classifier_cache_hits=hits,
            figures_processed=len(works),
        )

    async def _classify_block(
        self, ctx: IngestStageEnrichStepClassifyContext, block: Block
    ) -> tuple[FigureWork | None, bool]:
        """
        Download + classify one figure block into a FigureWork.

        Args:
            ctx (IngestStageEnrichStepClassifyContext): The resolved step context.
            block (Block): The FIGURE block to classify (has a non-empty crop_key).

        Returns:
            tuple[FigureWork | None, bool]: The seeded work item (None when the crop download failed)
                and whether the classification was a provider-call cache hit.
        """
        crop_key = block.figure.crop_key

        # 1. Download the crop. A failure skips the figure entirely (block untouched, not counted) -
        # the same behaviour as the legacy FigureEnricher download guard.
        try:
            crop_bytes = await ctx.object_store.download(crop_key)
        except Exception as exc:
            self.logger.warning(
                f"Enrich: could not download crop for block={block.id}: {exc} - skipping"
            )
            return None, False
        crop_hash = hashlib.sha256(crop_bytes).hexdigest()

        # 2. Classify (cached on the crop hash); a None classification falls back to PHOTO/0.0.
        classification, cls_trace, was_hit = await CacheRunner.run_classify(
            ctx.classifier_chain, ctx.provider_cache, crop_bytes, crop_hash
        )
        if classification is None:
            kind, relevance = FigureKind.PHOTO, 0.0
        else:
            kind, relevance = classification.kind, classification.confidence

        # 3. Resolve the routing decision once + build the work item.
        decision = EnrichRouting.decide(
            kind, self._ocr_enabled, self._vlm_enabled, self._chart_to_data
        )
        work = FigureWork(
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
        return work, was_hit


__all__ = ["IngestStageEnrichStepClassify"]
