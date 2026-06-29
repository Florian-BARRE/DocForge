# ====== Code Summary ======
# ContextualizeStage — the native contextualize (S5) stage. Assembly-only: it DECLARES the forced
# ClassVars (matching the former s5 contextualize adapter byte-for-byte) and wires its single
# ContextualizeStep (a PURE-LOGIC, non-chain step) around the injected contextualization
# implementation. CACHE_POLICY is IDEMPOTENT_WRITE, so it is never node-cached and needs no
# fingerprint override.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage

# ====== Local Project Imports ======
from .steps.contextualize_step import ContextualizeStep


@register_stage
class ContextualizeStage(IngestStage):
    """
    Native contextualize stage — builds each chunk's embed_text via its single ContextualizeStep.

    Declares the contextualize contract (identity/ordering/IO/cache/error) and assembles its
    pure-logic step around the contextualization implementation; the run/track/fingerprint/describe
    machinery is inherited.
    """

    KEY: ClassVar[str] = "contextualize"
    NAME: ClassVar[str] = "Contextualize"
    DESCRIPTION: ClassVar[str] = (
        "Build each chunk's embed_text from the document title, heading breadcrumb, and chunk "
        "body."
    )
    AFTER: ClassVar[tuple[str, ...]] = ("chunk",)
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("chunks", "ir")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s5_result", "chunks")
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.IDEMPOTENT_WRITE
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC

    def __init__(self, inner: S5ContextualizeStage) -> None:
        """
        Wire the stage around a contextualization implementation and build its single step.

        Args:
            inner (S5ContextualizeStage): The contextualization implementation. Retained as
                ``self._inner`` so the assembler/parity checks can reach it.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [ContextualizeStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single native contextualize step."""
        return self._steps


__all__ = ["ContextualizeStage"]
