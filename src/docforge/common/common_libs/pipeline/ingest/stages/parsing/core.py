# ====== Code Summary ======
# ParsingStage — the native parse stage (the canonical exemplar of the physical reorg). It is
# assembly-only: it DECLARES the forced ClassVars (identity/ordering/IO/cache/error — matching the
# former s1 parse adapter byte-for-byte) and wires its single ParseStep around the injected parse
# implementation. All execution logic is inherited from IngestStage -> AbstractStage.
#
# Parity contract (must equal the old s1 adapter): KEY="parse", key=StageKey.PARSE, AFTER=("ingest",),
# CONSUMES=("ingest_result",), PRODUCES=("parse_result","ir"), CACHE_POLICY=NODE_CACHED, ON_ERROR=FAIL_DOC,
# code_version="1.0", and fingerprint_params()={"parse_chain": <signature>}. key=StageKey.PARSE + the
# overridden fingerprint_params reproduce the legacy S1 node-cache key + markdown-blob fingerprint.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy, StageKey, StageSpec
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

    SPEC: ClassVar[StageSpec] = StageSpec(
        key=StageKey.PARSE,
        name="Parse",
        description=(
            "Parse the PDF into the canonical IR via the parser chain, render figure crops, and "
            "serialise the markdown view."
        ),
        after=(StageKey.INGEST,),
        consumes=("ingest_result",),
        produces=("parse_result", "ir"),
        cache_policy=CachePolicy.NODE_CACHED,
        error_policy=ErrorPolicy.FAIL_DOC,
    )

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
        node-cache key exactly (combined with ``key=StageKey.PARSE`` and ``code_version="1.0"``). Any
        change to a parser provider/version invalidates the parse node.

        Returns:
            dict[str, Any]: ``{"parse_chain": <chain signature>}``.
        """
        return {"parse_chain": self._inner.parse_chain.signature()}


__all__ = ["ParsingStage"]
