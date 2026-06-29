# ====== Code Summary ======
# IngestStageMetagenStepDocScope — the document-scope metagen step. It generates a single combined
# strict JSON call over a (title + truncated-body) digest of the IR, returning the non-null generated
# values as ``doc_fields`` (merged into doc_meta by the assemble step). All document-scope targets
# share one schema + one rule block; the call deduplicates through the provider cache. When the budget
# gate says not to proceed, the step returns empty doc_fields (full no-op).

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import MetaFieldSpec
from common_libs.pipelines import ChainRef, NodeSpec, ServiceRef

# ====== Local Project Imports ======
from ..base import (
    IngestStageMetagenStepBase,
    MetagenCallHelpers,
    MetagenPromptHelpers,
    MetagenSchemaBuilder,
)
from .context import IngestStageMetagenStepDocScopeContext
from .errors import IngestStageMetagenStepDocScopeError
from .io import (
    IngestStageMetagenStepDocScopeInput,
    IngestStageMetagenStepDocScopeOutput,
)


class IngestStageMetagenStepDocScope(IngestStageMetagenStepBase):
    """
    Generate document-scope metadata: one combined structured call over a title + digest.

    Reads the IR + the budget-gate proceed flag; writes the document-scope ``doc_fields``, the count
    generated, and the chain trace.
    """

    SPEC = NodeSpec(
        key="doc_scope",
        name="Document scope",
        description="Per-document LLM metadata generation into doc_fields.",
    )
    Input = IngestStageMetagenStepDocScopeInput
    Output = IngestStageMetagenStepDocScopeOutput
    Context = IngestStageMetagenStepDocScopeContext
    Error = IngestStageMetagenStepDocScopeError
    REQUIRES = (
        ChainRef(name="llm_chain", category="llm", description="Ordered LLM provider chain."),
        ServiceRef(name="provider_cache", description="Cross-document provider-call cache."),
    )

    def __init__(
        self,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
    ) -> None:
        """
        Wire the document-scope step with its assembly-time config.

        Args:
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
        """
        super().__init__()
        self._targets = targets
        self._field_types = field_types

    async def execute(
        self, ctx: IngestStageMetagenStepDocScopeContext
    ) -> IngestStageMetagenStepDocScopeOutput:
        """
        Generate document-scope metadata, or return empty doc_fields when not proceeding.

        Args:
            ctx (IngestStageMetagenStepDocScopeContext): Typed input + the chain + the cache.

        Returns:
            IngestStageMetagenStepDocScopeOutput: The doc_fields + count generated + chain trace.
        """
        # 1. No-op when the budget gate declined, or when there is no document-scope target.
        targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "document")
        if not ctx.input.proceed or not targets:
            return IngestStageMetagenStepDocScopeOutput()

        # 2. One strict schema + one rule block + the title/digest prompt for the single call.
        ir = ctx.input.ir
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenPromptHelpers.field_rules(targets, self._field_types)
        body = MetagenPromptHelpers.document_digest(ir)
        prompt = MetagenPromptHelpers.build_doc_prompt(rules, getattr(ir, "title", ""), body)

        # 3. Run the single cached call and keep the non-null generated values.
        data, outcome = await MetagenCallHelpers.call_cached(
            ctx.llm_chain, ctx.provider_cache, rules, prompt, schema, body
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
        return IngestStageMetagenStepDocScopeOutput(
            doc_fields=doc_fields, n_generated=len(doc_fields), chain_trace=trace
        )


__all__ = ["IngestStageMetagenStepDocScope"]
