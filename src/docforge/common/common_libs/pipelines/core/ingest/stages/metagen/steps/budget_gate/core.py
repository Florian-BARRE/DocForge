# ====== Code Summary ======
# IngestStageMetagenStepBudgetGate — the first metagen step. It reproduces the legacy S5b no-op +
# budget short-circuit: it returns proceed=False when there is no provider or no resolvable target,
# and when the estimated per-document spend exceeds the cap (leaving the fields empty rather than
# failing the document). Otherwise it returns proceed=True with the cost estimate. The targets +
# field-type lookup are assembly-time constructor args; the LLM chain is its only required service.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import MetaFieldSpec
from common_libs.pipelines import ChainRef, NodeSpec

# ====== Local Project Imports ======
from ..base import IngestStageMetagenStepBase, MetagenPromptHelpers
from .context import IngestStageMetagenStepBudgetGateContext
from .errors import IngestStageMetagenStepBudgetGateError
from .io import (
    IngestStageMetagenStepBudgetGateInput,
    IngestStageMetagenStepBudgetGateOutput,
)


class IngestStageMetagenStepBudgetGate(IngestStageMetagenStepBase):
    """
    Decide whether the metagen scopes run, given the provider, targets, and per-document budget.

    Reads the chunks + IR from the parent stage input; writes a ``proceed`` flag and the cost
    estimate. Never fails the document for being over budget — it returns ``proceed=False`` so the
    scope steps become passthroughs.
    """

    SPEC = NodeSpec(
        key="budget_gate",
        name="Budget gate",
        description="No-op + budget short-circuit for the metagen scopes.",
    )
    Input = IngestStageMetagenStepBudgetGateInput
    Output = IngestStageMetagenStepBudgetGateOutput
    Context = IngestStageMetagenStepBudgetGateContext
    Error = IngestStageMetagenStepBudgetGateError
    REQUIRES = (ChainRef(name="llm_chain", category="llm", description="Ordered LLM provider chain."),)

    def __init__(
        self,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Wire the budget gate with its assembly-time config.

        Args:
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
            max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
        """
        super().__init__()
        self._targets = targets
        self._field_types = field_types
        self._max_budget_usd = max_budget_usd

    async def execute(
        self, ctx: IngestStageMetagenStepBudgetGateContext
    ) -> IngestStageMetagenStepBudgetGateOutput:
        """
        Evaluate the no-op + budget short-circuit and return the proceed flag + cost estimate.

        Args:
            ctx (IngestStageMetagenStepBudgetGateContext): Typed input + the LLM chain.

        Returns:
            IngestStageMetagenStepBudgetGateOutput: proceed flag + estimated cost.
        """
        # 1. No-op short-circuit — no provider or no bindings means nothing to generate.
        chunk_targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "chunk")
        doc_targets = MetagenPromptHelpers.scope_targets(
            self._targets, self._field_types, "document"
        )
        if not ctx.llm_chain.providers or not self._targets or (not chunk_targets and not doc_targets):
            return IngestStageMetagenStepBudgetGateOutput(proceed=False, est_cost_usd=0.0)

        # 2. Estimate the per-document spend over both scopes.
        est_cost = MetagenPromptHelpers.estimate_total(
            ctx.input.chunks, chunk_targets, doc_targets, ctx.input.ir, self._field_types
        )

        # 3. Budget gate — degrade (leave empty) when the estimate exceeds the cap.
        if self._max_budget_usd > 0 and est_cost > self._max_budget_usd:
            doc_id = getattr(ctx.input.ir, "doc_id", "?")
            self.logger.warning(
                f"Metagen skipped: estimated cost ${est_cost:.4f} exceeds budget "
                f"${self._max_budget_usd:.4f} (doc_id={doc_id}) -- leaving fields empty."
            )
            return IngestStageMetagenStepBudgetGateOutput(proceed=False, est_cost_usd=est_cost)

        # 4. Proceed — the scopes run with the cost estimate carried into the result.
        return IngestStageMetagenStepBudgetGateOutput(proceed=True, est_cost_usd=est_cost)


__all__ = ["IngestStageMetagenStepBudgetGate"]
