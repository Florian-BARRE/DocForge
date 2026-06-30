# ====== Code Summary ======
# MetagenDocScope — the document-scope metagen node. It generates a single combined strict JSON call
# over a (title + truncated-body) digest of the IR, returning the non-null generated values as
# ``doc_fields`` (merged into doc_meta by the assemble node). All document-scope targets share one
# schema + one rule block; the call deduplicates through the injected provider cache. When the budget
# gate says not to proceed, the node returns empty doc_fields (full no-op).

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import ChainTrace, DocumentIR, MetaFieldSpec
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)

# ====== Local Project Imports ======
from ..helpers import MetagenCallHelpers, MetagenPromptHelpers, MetagenSchemaBuilder


class MetagenDocScopeInput(NodeInput):
    """
    Input of the document-scope node.

    Attributes:
        ir (DocumentIR): The enriched IR (from the metagen stage input) — digest source.
        proceed (bool): The budget-gate decision (from the budget-gate node).
    """

    ir: Annotated[DocumentIR, FromGroupInput()]
    proceed: Annotated[bool, FromNode("budget_gate", "proceed")]


class MetagenDocScopeOutput(NodeOutput):
    """
    Output of the document-scope node.

    Attributes:
        doc_fields (dict): Document-scope generated values ``{field_name: value}``.
        n_generated (int): Count of document-scope generated values written.
        chain_trace (ChainTrace | None): The document-scope chain trace, or None when nothing ran.
    """

    doc_fields: dict = {}
    n_generated: int = 0
    chain_trace: ChainTrace | None = None


class MetagenDocScope(ActionNode):
    """
    Generate document-scope metadata: one combined structured call over a title + digest.

    Reads the IR + the budget-gate proceed flag; writes the document-scope ``doc_fields``, the count
    generated, and the chain trace.
    """

    Input = MetagenDocScopeInput
    Output = MetagenDocScopeOutput

    def __init__(
        self,
        node_id: str,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
    ) -> None:
        """
        Wire the document-scope node with its assembly-time config.

        Args:
            node_id (str): The node's id (unique among its siblings).
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
        """
        super().__init__(node_id)
        self._targets = targets
        self._field_types = field_types

    async def execute(self, ctx: Context) -> MetagenDocScopeOutput:
        """
        Generate document-scope metadata, or return empty doc_fields when not proceeding.

        Args:
            ctx (Context): The resolved input + the injected ``llm_chain`` + ``provider_cache``.

        Returns:
            MetagenDocScopeOutput: The doc_fields + count generated + chain trace.
        """
        # 1. No-op when the budget gate declined, or when there is no document-scope target.
        targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "document")
        if not ctx.input.proceed or not targets:
            return MetagenDocScopeOutput()

        # 2. One strict schema + one rule block + the title/digest prompt for the single call.
        ir = ctx.input.ir
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenPromptHelpers.field_rules(targets, self._field_types)
        body = MetagenPromptHelpers.document_digest(ir)
        prompt = MetagenPromptHelpers.build_doc_prompt(rules, getattr(ir, "title", ""), body)

        # 3. Run the single cached call and keep the non-null generated values.
        data, outcome = await MetagenCallHelpers.call_cached(
            ctx.service("llm_chain"), ctx.service("provider_cache"), rules, prompt, schema, body
        )
        doc_fields: dict[str, Any] = {}
        for key, value in data.items():
            if value is not None:
                doc_fields[key] = value
        trace = MetagenCallHelpers.to_chain_trace(outcome) if outcome is not None else None

        self.logger.info(
            f"Metagen doc-scope: generated={len(doc_fields)} targets={len(targets)} "
            f"doc_id={getattr(ir, 'doc_id', '?')}"
        )
        return MetagenDocScopeOutput(
            doc_fields=doc_fields, n_generated=len(doc_fields), chain_trace=trace
        )


__all__ = ["MetagenDocScope", "MetagenDocScopeInput", "MetagenDocScopeOutput"]
