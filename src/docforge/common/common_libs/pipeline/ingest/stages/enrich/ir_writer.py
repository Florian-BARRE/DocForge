# ====== Code Summary ======
# EnrichIRWriter — rebuilds the DocumentIR from the per-figure EnrichScratch and assembles the
# EnrichResult, then commits both onto the PipelineContext. Every capability step calls ``commit`` at
# the end so each step genuinely produces an updated IR (the partial enrichment is observable between
# steps) and a current EnrichResult — and the LAST step that runs (always at least the classify step)
# leaves the complete enriched IR + final counters on the context. Only figure blocks present in the
# scratch are rewritten; every other block (non-figure, crop-less, or a figure whose crop failed to
# download) passes through untouched, exactly as the legacy per-figure path left them.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

# ====== Local Project Imports ======
from .result import EnrichResult

if TYPE_CHECKING:
    from common_libs.domain.ir.models import DocumentIR
    from common_libs.pipeline.stages.context import PipelineContext

    from .result import EnrichCounters
    from .scratch import EnrichScratch


class EnrichIRWriter:
    """
    Static helper that materialises the enrich scratch onto the IR and the context.

    ``apply`` rebuilds the IR's figure blocks from the scratch; ``build_result`` snapshots the
    counters into an :class:`EnrichResult`; ``commit`` does both and writes them onto the context.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("EnrichIRWriter is a static-only class and cannot be instantiated.")

    @staticmethod
    def apply(ir: "DocumentIR", scratch: "EnrichScratch") -> "DocumentIR":
        """
        Rebuild the IR with each scratch figure's current enrichment + accumulated traces.

        Args:
            ir (DocumentIR): The IR to rewrite (its blocks are copied, never mutated in place).
            scratch (EnrichScratch): The per-figure work, keyed by block id.

        Returns:
            DocumentIR: A copy of ``ir`` with the enrichable figure blocks updated; all other
                blocks are passed through unchanged.
        """
        # 1. Rewrite only the figure blocks the classify step recorded; pass everything else through.
        new_blocks = []
        for block in ir.blocks:
            work = scratch.figures.get(block.id)
            if work is None:
                new_blocks.append(block)
                continue
            new_blocks.append(
                block.model_copy(update={"figure": work.enrichment(), "chain_traces": work.traces()})
            )

        # 2. Assemble the enriched IR copy (same shape as the legacy ``ir.model_copy(update=blocks)``).
        return ir.model_copy(update={"blocks": new_blocks})

    @staticmethod
    def build_result(ir: "DocumentIR", counters: "EnrichCounters") -> EnrichResult:
        """
        Snapshot the run counters into the immutable EnrichResult contract.

        Args:
            ir (DocumentIR): The (current) enriched IR.
            counters (EnrichCounters): The run-level accounting accumulator.

        Returns:
            EnrichResult: The enrich stage output contract.
        """
        return EnrichResult(
            ir=ir,
            figures_processed=counters.figures_processed,
            ocr_calls=counters.ocr_calls,
            vlm_calls=counters.vlm_calls,
            chart_extractions=counters.chart_extractions,
            ocr_cache_hits=counters.ocr_cache_hits,
            vlm_cache_hits=counters.vlm_cache_hits,
            classifier_calls=counters.classifier_calls,
            classifier_cache_hits=counters.classifier_cache_hits,
        )

    @classmethod
    def commit(cls, ctx: "PipelineContext", scratch: "EnrichScratch") -> None:
        """
        Apply the scratch onto ``ctx.ir`` and write the current EnrichResult onto the context.

        Idempotent and called by every capability step: re-applying the scratch is cheap (documents
        carry few figures) and keeps the produced IR + result current after each pass, so the final
        step leaves the complete enriched output regardless of which optional steps were built.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
            scratch (EnrichScratch): The per-figure work + run counters.
        """
        ctx.ir = cls.apply(ctx.ir, scratch)
        ctx.enrich_result = cls.build_result(ctx.ir, scratch.counters)


__all__ = ["EnrichIRWriter"]
