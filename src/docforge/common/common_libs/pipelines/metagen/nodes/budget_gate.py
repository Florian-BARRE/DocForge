# ====== Code Summary ======
# MetagenBudgetGate — the first metagen node. It reproduces the no-op + budget short-circuit: it
# returns proceed=False when there is no LLM provider or no resolvable target, and when the estimated
# per-document spend exceeds the cap (leaving the fields empty rather than failing the document).
# Otherwise it returns proceed=True with the cost estimate. The targets + field-type lookup are
# assembly-time constructor args; the LLM chain is its only injected service (``llm_chain``), consulted
# for its provider list only — this node issues no LLM call.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import Chunk, DocumentIR, MetaFieldSpec
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    NodeInput,
    NodeOutput,
)

# ====== Local Project Imports ======
from ..helpers import MetagenPromptHelpers


class MetagenBudgetGateInput(NodeInput):
    """
    Input of the budget-gate node (read from the metagen stage input).

    Attributes:
        chunks (list[Chunk]): The document's chunks (chunk-scope cost driver).
        ir (DocumentIR): The enriched IR (document-scope digest source).
    """

    chunks: Annotated[list[Chunk], FromGroupInput()]
    ir: Annotated[DocumentIR, FromGroupInput()]


class MetagenBudgetGateOutput(NodeOutput):
    """
    Output of the budget-gate node.

    Attributes:
        proceed (bool): True when the metagen scopes should run; False on a no-op or over-budget.
        est_cost_usd (float): Estimated LLM spend for this document's metagen calls.
    """

    proceed: bool
    est_cost_usd: float = 0.0


class MetagenBudgetGate(ActionNode):
    """
    Decide whether the metagen scopes run, given the provider, targets, and per-document budget.

    Never fails the document for being over budget — it returns ``proceed=False`` so the scope nodes
    become passthroughs.
    """

    Input = MetagenBudgetGateInput
    Output = MetagenBudgetGateOutput

    def __init__(
        self,
        node_id: str,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Wire the budget gate with its assembly-time config.

        Args:
            node_id (str): The node's id (unique among its siblings).
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
            max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
        """
        super().__init__(node_id)
        self._targets = targets
        self._field_types = field_types
        self._max_budget_usd = max_budget_usd

    async def execute(self, ctx: Context) -> MetagenBudgetGateOutput:
        """
        Evaluate the no-op + budget short-circuit and return the proceed flag + cost estimate.

        Args:
            ctx (Context): The resolved input (chunks + IR) and the injected ``llm_chain`` service.

        Returns:
            MetagenBudgetGateOutput: proceed flag + estimated cost.
        """
        # 1. No-op short-circuit — no provider or no bindings means nothing to generate.
        chunk_targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "chunk")
        doc_targets = MetagenPromptHelpers.scope_targets(
            self._targets, self._field_types, "document"
        )
        chain = ctx.service("llm_chain")
        if (
            chain is None
            or not chain.providers
            or not self._targets
            or (not chunk_targets and not doc_targets)
        ):
            return MetagenBudgetGateOutput(proceed=False, est_cost_usd=0.0)

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
            return MetagenBudgetGateOutput(proceed=False, est_cost_usd=est_cost)

        # 4. Proceed — the scopes run with the cost estimate carried into the result.
        return MetagenBudgetGateOutput(proceed=True, est_cost_usd=est_cost)


__all__ = ["MetagenBudgetGate", "MetagenBudgetGateInput", "MetagenBudgetGateOutput"]
