# ====== Code Summary ======
# EnrichStage — the native enrich (S2) stage. Assembly-only: it DECLARES the forced ClassVars
# (matching the former s2 enrich adapter byte-for-byte) and wires its single executing EnrichStep
# around the injected enrichment implementation. fingerprint_params surfaces the legacy S2 params
# (classifier/OCR/VLM chain signatures + chart_to_data) and NODE_TYPE="s2" pins the legacy node id,
# so the node-cache key is byte-identical to the old engine.
#
# describe() is OVERRIDDEN to model the FOUR conceptual sub-steps (classify -> ocr -> vlm -> chart),
# conditional on which chains exist + chart_to_data, so the self-describing API surfaces the S2
# structure. Execution stays fused in EnrichStep (per-figure routing is atomic — see that module);
# the four schemas are descriptive only. The true execution-level split is a later inner-stage
# refactor increment.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import register_stage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy, StageSchema
from common_libs.pipeline.base.step.core import AbstractStep
from common_libs.pipeline.base.step.model import StepSchema
from common_libs.pipeline.ingest.stages.base.stage import IngestStage
from common_libs.pipeline.stages.s2_enrich.core import S2EnrichStage
from common_libs.pipeline.bricks.chain import ChainHelpers

# ====== Local Project Imports ======
from .steps.enrich_step import EnrichStep


@register_stage
class EnrichStage(IngestStage):
    """
    Native enrich stage — classifies + routes figures via its single executing EnrichStep.

    Declares the enrich contract (identity/ordering/IO/cache/error), pins the legacy ``s2`` node id,
    and surfaces its four conceptual sub-steps (classify/ocr/vlm/chart) through ``describe()``.
    """

    KEY: ClassVar[str] = "enrich"
    NAME: ClassVar[str] = "Enrich"
    DESCRIPTION: ClassVar[str] = (
        "Classify each figure and route it through OCR / VLM / chart-to-data chains, enriching "
        "the IR in place."
    )
    AFTER: ClassVar[tuple[str, ...]] = ("parse",)
    CONFIG: ClassVar[None] = None
    CONSUMES: ClassVar[tuple[str, ...]] = ("s1_result", "ir")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s2_result", "ir")
    CACHE_POLICY: ClassVar[CachePolicy] = CachePolicy.NODE_CACHED
    ON_ERROR: ClassVar[ErrorPolicy] = ErrorPolicy.FAIL_DOC
    # Legacy node id/type so the fingerprint hex + stage_run rows match the old engine exactly.
    NODE_TYPE: ClassVar[str] = "s2"

    def __init__(self, inner: S2EnrichStage) -> None:
        """
        Wire the stage around an enrichment implementation and build its single executing step.

        Args:
            inner (S2EnrichStage): The enrichment implementation. Retained as ``self._inner`` so the
                assembler/parity checks (and ``describe()``) can reach its chains.
        """
        IngestStage.__init__(self)
        self._inner = inner
        self._steps: list[AbstractStep] = [EnrichStep(inner)]

    @property
    def steps(self) -> list[AbstractStep]:
        """The single executing enrich step (per-figure routing is fused inside it)."""
        return self._steps

    def fingerprint_params(self) -> dict[str, object]:
        """
        Surface the legacy S2 node fingerprint params (classifier/OCR/VLM signatures + chart flag).

        Overrides the inherited step-aggregate so the dynamic engine reproduces the legacy S2
        node-cache key exactly (with ``NODE_TYPE="s2"`` and ``NODE_VERSION="1.0"``). Delegates to the
        inner stage's own ``params_for_fingerprint`` (mirrors ``S012ParamHelpers.s2_params``).

        Returns:
            dict[str, object]: The legacy S2 fingerprint parameter dict.
        """
        return self._inner.params_for_fingerprint()

    def describe(self) -> StageSchema:
        """
        Emit the stage schema with the FOUR conceptual sub-steps modeled (descriptive only).

        The sub-steps mirror S2's per-figure routing ladder: classify (always), then OCR / VLM
        (each present only when its chain is configured), then chart-to-data (only when enabled).
        Execution remains fused in ``EnrichStep`` for byte-identical parity.

        Returns:
            StageSchema: Identity + IO + policy + the conceptual step schemas.
        """
        return StageSchema(
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            after=list(self.AFTER),
            consumes=list(self.CONSUMES),
            produces=list(self.PRODUCES),
            cache_policy=self.CACHE_POLICY,
            on_error=self.ON_ERROR,
            config=None,
            steps=self._conceptual_steps(),
        )

    def _conceptual_steps(self) -> list[StepSchema]:
        """
        Build the conceptual sub-step schemas from the inner stage's configured chains.

        Returns:
            list[StepSchema]: classify (+ ocr/vlm when configured, + chart when enabled).
        """
        # 1. Classify is always present (the routing entry point).
        steps = [self._chain_schema("classify", "Classify", "Classify each figure's type.", self._inner._classifier_chain)]

        # 2. OCR / VLM appear only when their chain is configured (mirrors the routing table).
        if self._inner._ocr_chain is not None:
            steps.append(self._chain_schema("ocr", "OCR", "Extract text from text-bearing figures.", self._inner._ocr_chain))
        if self._inner._vlm_chain is not None:
            steps.append(self._chain_schema("vlm", "VLM", "Describe figures via a vision-language model.", self._inner._vlm_chain))

        # 3. Chart-to-data is a conditional sub-step (no separate provider family).
        if self._inner._chart_to_data:
            steps.append(StepSchema(
                kind="step", key="chart", name="Chart-to-data",
                description="Extract structured data tables from CHART figures.",
                consumes=["ir"], produces=["ir"],
            ))
        return steps

    @staticmethod
    def _chain_schema(key: str, name: str, description: str, chain: object) -> StepSchema:
        """Build a chain-kind StepSchema (category + ordered provider ids) for a routing chain."""
        return StepSchema(
            kind="chain", key=key, name=name, description=description,
            consumes=["ir"], produces=["ir"], category=key,
            providers=[ChainHelpers.default_provider_id(p) for p in chain.providers],  # type: ignore[attr-defined]
        )


__all__ = ["EnrichStage"]
