# ====== Code Summary ======
# EnrichStep — the single executing step of the enrich (S2) stage. It reads the parse result + the
# current IR from the context, delegates to the existing S2EnrichStage (per-figure classify ->
# route -> OCR/VLM/chart, with the provider-call cache + the run-level counters), and writes the
# S2Result + the enriched IR back.
#
# WHY ONE STEP (not four): S2's routing is per-figure and ATOMIC — each figure is classified and
# then routed through OCR/VLM/chart inside one FigureEnricher.process_block call, with the
# provider-call cache hits and the figures-processed/cache-hit counters interleaved per block.
# Re-expressing that as four whole-IR passes would change the iteration model + cache/counter
# semantics (a logic rewrite, not a structural move), breaking byte-identical parity. The four
# conceptual sub-steps are therefore surfaced via EnrichStage.describe(), while execution stays
# fused here. The true execution-level split belongs to a dedicated inner-stage refactor increment.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s2_enrich.core import S2EnrichStage


class EnrichStep(IngestStep):
    """
    Native enrich step — delegates to the legacy S2 enrichment logic, threading IO via the context.

    Reads ``parse_result`` + ``ir``; writes ``enrich_result`` and the enriched ``ir``.
    """

    KEY: ClassVar[str] = "enrich"
    NAME: ClassVar[str] = "Enrich"
    DESCRIPTION: ClassVar[str] = (
        "Classify each figure and route it through OCR / VLM / chart-to-data chains, enriching "
        "the IR in place."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("parse_result", "ir")
    PRODUCES: ClassVar[tuple[str, ...]] = ("enrich_result", "ir")

    def __init__(self, enricher: "S2EnrichStage") -> None:
        """
        Wire the step around the enrichment implementation.

        Args:
            enricher (S2EnrichStage): The enrichment implementation (classifier/OCR/VLM chains).
        """
        IngestStep.__init__(self)
        self._enricher = enricher

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the enrichment implementation and write its output onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Enrich the figures of the current IR (per-figure classify + route, byte-identical).
        result = await self._enricher.run(ctx.parse_result, ctx.ir)

        # 2. Write the declared PRODUCES back; the enriched IR replaces the prior one.
        ctx.enrich_result = result
        ctx.ir = result.ir


__all__ = ["EnrichStep"]
