# ====== Code Summary ======
# ParseStep — the first parse step and the chain-backed one. It drives the parser provider chain
# (docling / mineru / …) over the derived PDF: the first provider whose IR passes the gate wins.
# It stamps the parse ChainTrace onto the IR (lineage), and on a degraded exhaustion under
# failure_policy=continue substitutes a minimal empty IR. The accepted (or empty) IR is written to
# ``ctx.ir`` and the degraded flag is seeded onto the parse scratch for the later steps. Modelled as
# an IngestStep that owns the chain (one ``Chain.call`` per run) and surfaces the per-attempt lineage
# to the tracking layer + a chain-kind describe() so the self-describing API shows the parser ladder.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.bricks.chain import ChainAttempt, ChainHelpers
from common_libs.pipeline.ingest.stages.base.step import IngestStep

# ====== Local Project Imports ======
from ..helpers import ParseHelpers
from ..scratch import PARSE_SCRATCH_KEY, ParseScratch

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.chain import Chain, ChainOutcome
    from common_libs.pipeline.stages.context import PipelineContext


class ParseStep(IngestStep):
    """
    Native parse step — drives the parser chain into the canonical IR and stamps its lineage.

    Reads ``ingest_result`` (the derived PDF + identity); writes the canonical ``ir`` and seeds
    ``ctx.aux["parse_scratch"]`` (the degraded flag) for the figure-render + markdown steps.
    """

    KEY: ClassVar[str] = "parse"
    NAME: ClassVar[str] = "Parse"
    DESCRIPTION: ClassVar[str] = (
        "Drive the parser chain over the derived PDF into the canonical IR; the first provider "
        "whose quality passes the gate wins. The parse lineage is stamped onto the IR."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ingest_result",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", PARSE_SCRATCH_KEY)

    def __init__(self, parse_chain: "Chain[Any, Any]") -> None:
        """
        Wire the step around the parser escalation chain.

        Args:
            parse_chain (Chain[Any, Any]): Ordered parser chain (docling, …); index 0 is tried
                first, the gate decides escalation.
        """
        IngestStep.__init__(self)
        self._chain = parse_chain
        self._last_outcome: "ChainOutcome | None" = None

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the parser chain, resolve the canonical IR, and seed the parse scratch.

        Args:
            ctx (PipelineContext): The mutable run accumulator.

        Raises:
            ChainExhaustedError: When every parser escalates/raises AND the parse gate's
                ``failure_policy="raise"`` (the default). The worker fail-closed boundary marks the
                doc ``failed``. Under ``failure_policy="continue"`` a degraded (empty-IR) outcome is
                produced instead and the document proceeds with zero blocks.
        """
        # 1. Read the ingest result (the derived PDF + identity are the parser inputs).
        s0 = ctx.ingest_result
        self.logger.info(f"Parse started: doc_id={s0.doc_id} pages={s0.page_count}")

        # 2. Run the parser chain — each provider produces a full DocumentIR; the chain stops at the
        # first whose quality_score passes the gate. On exhaustion the chain applies its failure
        # policy (raise → propagates; continue → degraded outcome with result=None, handled below).
        outcome = await self._chain.call(
            lambda p: p.parse(
                pdf_bytes=s0.pdf_bytes,
                doc_id=s0.doc_id,
                source_hash=s0.source_hash,
            )
        )
        self._last_outcome = outcome

        # 3. Resolve the IR: a degraded (result=None) outcome substitutes a minimal empty IR so the
        # document ends "done" with no blocks (the expert's explicit failure_policy=continue choice).
        degraded = outcome.result is None
        if degraded:
            self.logger.warning(
                f"Parse chain degraded for doc_id={s0.doc_id} "
                f"({len(outcome.attempts)} provider(s) attempted, none produced an IR) — "
                f"continuing with an empty IR per the gate's failure_policy=continue."
            )
            ir = ParseHelpers.empty_ir(s0)
        else:
            ir = outcome.result

        # 4. Stamp the parse trace so every downstream consumer sees the lineage, then write ctx +
        # seed the cross-step scratch with the degraded flag for the markdown step.
        ctx.ir = ParseHelpers.stamp_parse_trace(ir, outcome)
        ctx.aux[PARSE_SCRATCH_KEY] = ParseScratch(degraded=degraded)
        self.logger.info(
            f"Parse chain done: doc_id={s0.doc_id} final_parser={outcome.final_provider} "
            f"attempts={len(outcome.attempts)} blocks={len(ctx.ir.blocks)}"
        )

    def fingerprint_params(self) -> dict[str, Any]:
        """Return the parser chain signature — any parser provider/version change invalidates parse."""
        return {"parse_chain": self._chain.signature()}

    def trace_attempts(self) -> list[ChainAttempt]:
        """Return the per-provider attempts captured by the last chain run."""
        return list(self._last_outcome.attempts) if self._last_outcome is not None else []

    def trace_final_provider(self) -> str | None:
        """Return the provider id whose IR the chain accepted on the last run."""
        return self._last_outcome.final_provider if self._last_outcome is not None else None

    def describe(self) -> StepSchema:
        """
        Emit a chain-kind schema (the parser provider category + ordered provider choices).

        Returns:
            StepSchema: Chain-kind identity + IO + the parser provider ids.
        """
        return StepSchema(
            kind="chain",
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            category="parse",
            providers=[ChainHelpers.default_provider_id(p) for p in self._chain.providers],
        )


__all__ = ["ParseStep"]
