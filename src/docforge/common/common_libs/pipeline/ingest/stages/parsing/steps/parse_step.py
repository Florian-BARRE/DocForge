# ====== Code Summary ======
# ParseStep — the single native step of the parsing stage. It reads the S0 ingest result and the
# parse-node fingerprint from the context, drives the parser chain (docling/mineru/tika) by
# delegating to the existing S1ParseStage.run, and writes the S1Result + the canonical IR back.
#
# INCREMENT-1 SCOPE: the step delegates to the whole S1ParseStage.run (chain → IR → figure crops →
# markdown upload) rather than calling the bare parser chain, because S1ParseStage does more than
# the chain alone (rendering + markdown serialization). Decomposing parse into a true ChainStep
# (chain-only) plus separate render/markdown steps is a LATER increment; here the structure is
# native (a real IngestStep in its own folder) while behaviour stays byte-identical to the adapter.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s1_parse.core import S1ParseStage


class ParseStep(IngestStep):
    """
    Native parse step — delegates to the legacy S1 parse logic, threading IO via the context.

    Reads ``ingest_result`` and the parse-node fingerprint (``ctx.fingerprints["parse"]`` — the same
    fingerprint that keys the markdown S3 blob, exactly as legacy ``run_s1`` passed ``s1_fp``);
    writes ``parse_result`` and the canonical ``ir``.
    """

    KEY: ClassVar[str] = "parse"
    NAME: ClassVar[str] = "Parse"
    DESCRIPTION: ClassVar[str] = (
        "Parse the PDF into the canonical IR via the parser chain, render figure crops, and "
        "serialise the markdown view."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ingest_result",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("parse_result", "ir")

    def __init__(self, parser: "S1ParseStage") -> None:
        """
        Wire the step around the parse stage implementation.

        Args:
            parser (S1ParseStage): The parse implementation (parser chain + renderer).
        """
        IngestStep.__init__(self)
        self._parser = parser

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the parser chain signature — any parser provider/version change invalidates parse.

        Returns:
            dict[str, Any]: ``{"parse_chain": <chain signature>}``.
        """
        return {"parse_chain": self._parser.parse_chain.signature()}

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the parse implementation and write its output onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Drive the parser. The fingerprint passed is THIS node's (parse) fingerprint — the
        # caching middleware populates ctx.fingerprints["parse"] before the stage runs, and that
        # value keys the markdown S3 blob (legacy run_s1 passed s1_fp for exactly this reason).
        result = await self._parser.run(ctx.ingest_result, ctx.fingerprints.get(self.KEY))

        # 2. Write the declared PRODUCES back onto the context.
        ctx.parse_result = result
        ctx.ir = result.ir


__all__ = ["ParseStep"]
