# ====== Code Summary ======
# The classify node - the first (always-present) action of the enrich stage. It reads the parsed IR
# (down from the enrich group input), downloads + classifies every enrichable FIGURE crop through the
# injected classifier chain (provider-call cached on the crop sha256), and records each figure's kind +
# relevance + the single routing DECISION (decorative / OCR / VLM / chart-schema) onto a FigureWork.
# It emits the classified IR plus the seeded work list (threaded onward to the OCR / VLM / chart nodes).
# The classifier chain, object store, and provider cache are injected services - never built here.

# ====== Standard Library Imports ======
import hashlib
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import Block, BlockType, DocumentIR, FigureKind
from common_libs.pipelines.core.ingest.stages.enrich.cache_runner import CacheRunner
from common_libs.pipelines.core.ingest.stages.enrich.figure_work import FigureWork
from common_libs.pipelines.core.ingest.stages.enrich.ir_builder import EnrichIRWriter
from common_libs.pipelines.core.ingest.stages.enrich.routing import EnrichRouting
from common_libs.pipelines.flow import ActionNode, Context, FromGroupInput, NodeInput, NodeOutput


class EnrichClassifyInput(NodeInput):
    """Input of the classify node - the parsed IR (down from the enrich group's input)."""

    ir: Annotated[DocumentIR, FromGroupInput()]


class EnrichClassifyOutput(NodeOutput):
    """Output of the classify node - the classified IR + the seeded per-figure work list + counters."""

    ir: DocumentIR
    figure_works: list[FigureWork]
    classifier_calls: int = 0
    classifier_cache_hits: int = 0
    figures_processed: int = 0


class EnrichClassify(ActionNode):
    """Classify every enrichable figure and record its OCR / VLM / chart routing decision."""

    Input = EnrichClassifyInput
    Output = EnrichClassifyOutput

    def __init__(
        self, node_id: str, ocr_enabled: bool, vlm_enabled: bool, chart_to_data: bool
    ) -> None:
        """
        Wire the node around the routing inputs (which capabilities are active).

        Args:
            node_id (str): The node's id among its siblings.
            ocr_enabled (bool): Whether an OCR chain is wired (drives the routing decision).
            vlm_enabled (bool): Whether a VLM chain is wired (drives the routing decision).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag (drives the chart-schema decision).
        """
        super().__init__(node_id)
        self._ocr_enabled = ocr_enabled
        self._vlm_enabled = vlm_enabled
        self._chart_to_data = chart_to_data

    async def execute(self, ctx: Context) -> EnrichClassifyOutput:
        """
        Classify each enrichable figure and seed the work list with the routing decisions.

        Args:
            ctx (Context): The resolved input (the IR) + the classifier chain / object store / cache.

        Returns:
            EnrichClassifyOutput: The classified IR + seeded work list + classifier counters.
        """
        # 1. Classify each enrichable FIGURE block; non-figure / crop-less blocks are not work items.
        ir = ctx.input.ir
        self.logger.info(f"Enrich classify: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}")
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
        return EnrichClassifyOutput(
            ir=classified_ir,
            figure_works=works,
            classifier_calls=calls,
            classifier_cache_hits=hits,
            figures_processed=len(works),
        )

    async def _classify_block(self, ctx: Context, block: Block) -> tuple[FigureWork | None, bool]:
        """
        Download + classify one figure block into a FigureWork.

        Args:
            ctx (Context): The resolved node context (carries the injected services).
            block (Block): The FIGURE block to classify (has a non-empty crop_key).

        Returns:
            tuple[FigureWork | None, bool]: The seeded work item (None when the crop download failed)
                and whether the classification was a provider-call cache hit.
        """
        # 1. Download the crop. A failure skips the figure entirely (block untouched, not counted) -
        # the same behaviour as the legacy FigureEnricher download guard.
        crop_key = block.figure.crop_key
        try:
            crop_bytes = await ctx.service("object_store").download(crop_key)
        except Exception as exc:
            self.logger.warning(f"Enrich: could not download crop for block={block.id}: {exc} - skipping")
            return None, False
        crop_hash = hashlib.sha256(crop_bytes).hexdigest()

        # 2. Classify (cached on the crop hash); a None classification falls back to PHOTO/0.0.
        classification, cls_trace, was_hit = await CacheRunner.run_classify(
            ctx.service("classifier_chain"), ctx.service("provider_cache"), crop_bytes, crop_hash
        )
        if classification is None:
            kind, relevance = FigureKind.PHOTO, 0.0
        else:
            kind, relevance = classification.kind, classification.confidence

        # 3. Resolve the routing decision once + build the work item.
        decision = EnrichRouting.decide(kind, self._ocr_enabled, self._vlm_enabled, self._chart_to_data)
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


__all__ = ["EnrichClassify", "EnrichClassifyInput", "EnrichClassifyOutput"]
