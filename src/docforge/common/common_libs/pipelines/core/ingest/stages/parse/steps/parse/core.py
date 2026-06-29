# ====== Code Summary ======
# IngestStageParseStepParse — the chain-backed parse step. It drives the parser provider chain
# (docling / mineru / ...) over the fetched PDF bytes: the first provider whose IR passes the gate
# wins. It stamps the parse ChainTrace onto the IR (lineage); on a degraded exhaustion under
# failure_policy=continue (or when there is no PDF view) it substitutes a minimal empty IR and flags
# the run degraded. It requires the parser chain service.

# ====== Internal Project Imports ======
from common_libs.pipelines import ChainRef, NodeSpec

# ====== Local Project Imports ======
from ...helpers import ParseHelpers
from ..base import IngestStageParseStepBase
from .context import IngestStageParseStepParseContext
from .errors import IngestStageParseStepParseError
from .io import IngestStageParseStepParseInput, IngestStageParseStepParseOutput


class IngestStageParseStepParse(IngestStageParseStepBase):
    """
    Drive the parser chain into the canonical IR and stamp its lineage.

    Reads the PDF bytes (fetch-pdf) + identity (stage input); writes the canonical IR and the degraded
    flag the figure-render and markdown steps branch on.
    """

    SPEC = NodeSpec(
        key="parse",
        name="Parse",
        description=(
            "Drive the parser chain over the PDF view into the canonical IR; the first provider "
            "whose quality passes the gate wins. The parse lineage is stamped onto the IR."
        ),
    )
    Input = IngestStageParseStepParseInput
    Output = IngestStageParseStepParseOutput
    Context = IngestStageParseStepParseContext
    Error = IngestStageParseStepParseError
    REQUIRES = (
        ChainRef(
            name="parser_chain",
            category="parser",
            description="Ordered parser escalation chain (docling, ...).",
        ),
    )

    async def execute(
        self, ctx: IngestStageParseStepParseContext
    ) -> IngestStageParseStepParseOutput:
        """
        Run the parser chain and resolve the canonical IR (or a degraded empty IR).

        Args:
            ctx (IngestStageParseStepParseContext): Typed input + the parser chain.

        Returns:
            IngestStageParseStepParseOutput: The canonical IR + the degraded flag.

        Raises:
            IngestStageParseStepParseError: When the chain exhausts under ``failure_policy="raise"``
                (the engine wraps the raw ``ChainExhaustedError`` in this typed error).
        """
        # 1. No PDF view -> there is nothing to parse; emit a degraded empty IR (no chain call).
        if ctx.input.pdf_bytes is None:
            self.logger.warning(
                f"Parse degraded for doc_id={ctx.input.doc_id}: no PDF view to parse - "
                f"continuing with an empty IR."
            )
            empty = ParseHelpers.empty_ir(
                ctx.input.doc_id, ctx.input.source_hash, ctx.input.page_count
            )
            return IngestStageParseStepParseOutput(ir=empty, degraded=True)

        # 2. Run the parser chain — each provider produces a full DocumentIR; the chain stops at the
        # first whose quality passes the gate. On exhaustion it applies its failure policy (raise ->
        # propagates and the engine wraps it; continue -> degraded outcome with result=None below).
        self.logger.info(
            f"Parse started: doc_id={ctx.input.doc_id} pages={ctx.input.page_count}"
        )
        outcome = await ctx.parser_chain.call(
            lambda p: p.parse(
                pdf_bytes=ctx.input.pdf_bytes,
                doc_id=ctx.input.doc_id,
                source_hash=ctx.input.source_hash,
            )
        )

        # 3. Resolve the IR: a degraded (result=None) outcome substitutes a minimal empty IR so the
        # document ends "done" with no blocks (the expert's explicit failure_policy=continue choice).
        degraded = outcome.result is None
        if degraded:
            self.logger.warning(
                f"Parse chain degraded for doc_id={ctx.input.doc_id} "
                f"({len(outcome.attempts)} provider(s) attempted, none produced an IR) - "
                f"continuing with an empty IR per the gate's failure_policy=continue."
            )
            ir = ParseHelpers.empty_ir(
                ctx.input.doc_id, ctx.input.source_hash, ctx.input.page_count
            )
        else:
            ir = outcome.result

        # 4. Stamp the parse trace so every downstream consumer sees the lineage.
        ir = ParseHelpers.stamp_parse_trace(ir, outcome)
        self.logger.info(
            f"Parse chain done: doc_id={ctx.input.doc_id} final_parser={outcome.final_provider} "
            f"attempts={len(outcome.attempts)} blocks={len(ir.blocks)}"
        )
        return IngestStageParseStepParseOutput(ir=ir, degraded=degraded)


__all__ = ["IngestStageParseStepParse"]
