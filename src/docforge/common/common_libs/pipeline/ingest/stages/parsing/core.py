# ====== Code Summary ======
# ParsingStage — the native parse stage (the canonical exemplar of the physical reorg). It is
# assembly-only: it DECLARES the forced ClassVars (identity/ordering/IO/cache/error — matching the
# former s1 parse adapter byte-for-byte) and wires its single ParseStep around the injected parse
# implementation. All execution logic is inherited from IngestStage -> AbstractStage.
#
# Parity contract (must equal the old s1 adapter): KEY="parse", NODE_TYPE="s1", AFTER=("ingest",),
# CONSUMES=("s0_result",), PRODUCES=("s1_result","ir"), CACHE_POLICY=NODE_CACHED, ON_ERROR=FAIL_DOC,
# NODE_VERSION="1.0", and fingerprint_params()={"parse_chain": <signature>}. NODE_TYPE="s1" + the
# overridden fingerprint_params reproduce the legacy S1 node-cache key + markdown-blob fingerprint.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage

# ====== Local Project Imports ======
from .steps.parse_step import ParseStep


@register_stage
class ParsingStage(IngestStage):
    """
    Native parse stage — drives the parser chain into the canonical IR via its single ParseStep.

    Declares the parse contract (identity/ordering/IO/cache/error) and assembles its step around
    the parse implementation; the run/track/fingerprint/describe machinery is inherited. Pinned to
    the legacy node id ``s1`` so its Merkle fingerprint + ``stage_run`` rows stay byte-identical to
    the legacy engine.
    """

    KEY: ClassVar[str] = "parse"
    NAME: ClassVar[str] = "Parse"
    DESCRIPTION: ClassVar[str] = (
        "Parse the PDF into the canonical IR via the parser chain, render figure crops, and "
        "serialise the markdown view."
    )
    AFTER: ClassVar[tuple[str, ...]] = ("ingest",)
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("s0_result",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("s1_result", "ir")
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.NODE_CACHED
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC
    # Legacy node id/type so the fingerprint hex + stage_run rows match the old engine exactly.
    NODE_TYPE: ClassVar[str] = "s1"

    def __init__(self, inner: S1ParseStage) -> None:
        """
        Wire the stage around a parse implementation and build its single step.

        Args:
            inner (S1ParseStage): The parse implementation (parser chain + renderer). Retained as
                ``self._inner`` so the assembler/parity checks can reach the inner chain.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [ParseStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single native parse step."""
        return self._steps

    def fingerprint_params(self) -> dict[str, Any]:
        """
        Surface the legacy S1 node fingerprint params (the parse chain signature).

        Overrides the inherited step-aggregate so the dynamic engine reproduces the legacy S1
        node-cache key exactly (combined with ``NODE_TYPE="s1"`` and ``NODE_VERSION="1.0"``). Any
        change to a parser provider/version invalidates the parse node.

        Returns:
            dict[str, Any]: ``{"parse_chain": <chain signature>}``.
        """
        return {"parse_chain": self._inner.parse_chain.signature()}


__all__ = ["ParsingStage"]
