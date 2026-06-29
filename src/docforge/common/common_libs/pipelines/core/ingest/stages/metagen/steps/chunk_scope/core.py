# ====== Code Summary ======
# IngestStageMetagenStepChunkScope — the chunk-scope metagen step. It generates one combined strict
# JSON call per chunk (run concurrently under a Semaphore), writing the non-null generated values into
# each ``chunk.derived_meta`` in place. All chunk-scope targets share one schema + one rule block
# (cacheable grammar); every call deduplicates through the provider cache. When the budget gate says
# not to proceed, the step passes the chunks through unchanged (full no-op).

# ====== Standard Library Imports ======
import asyncio
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
from .context import IngestStageMetagenStepChunkScopeContext
from .errors import IngestStageMetagenStepChunkScopeError
from .io import (
    IngestStageMetagenStepChunkScopeInput,
    IngestStageMetagenStepChunkScopeOutput,
)


class IngestStageMetagenStepChunkScope(IngestStageMetagenStepBase):
    """
    Generate chunk-scope metadata: one combined structured call per chunk under a Semaphore.

    Reads the chunks + the budget-gate proceed flag; writes the same chunks (with ``derived_meta``
    filled), the count generated, and one representative chain trace.
    """

    SPEC = NodeSpec(
        key="chunk_scope",
        name="Chunk scope",
        description="Per-chunk LLM metadata generation into chunk.derived_meta.",
    )
    Input = IngestStageMetagenStepChunkScopeInput
    Output = IngestStageMetagenStepChunkScopeOutput
    Context = IngestStageMetagenStepChunkScopeContext
    Error = IngestStageMetagenStepChunkScopeError
    REQUIRES = (
        ChainRef(name="llm_chain", category="llm", description="Ordered LLM provider chain."),
        ServiceRef(name="provider_cache", description="Cross-document provider-call cache."),
    )

    def __init__(
        self,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_concurrency: int = 8,
    ) -> None:
        """
        Wire the chunk-scope step with its assembly-time config.

        Args:
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
            max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
        """
        super().__init__()
        self._targets = targets
        self._field_types = field_types
        self._max_concurrency = max_concurrency

    async def execute(
        self, ctx: IngestStageMetagenStepChunkScopeContext
    ) -> IngestStageMetagenStepChunkScopeOutput:
        """
        Generate chunk-scope metadata, or pass the chunks through when not proceeding.

        Args:
            ctx (IngestStageMetagenStepChunkScopeContext): Typed input + the chain + the cache.

        Returns:
            IngestStageMetagenStepChunkScopeOutput: The chunks + count generated + representative trace.
        """
        # 1. No-op passthrough when the budget gate declined, or when there is no chunk-scope target.
        chunks = ctx.input.chunks
        targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "chunk")
        if not ctx.input.proceed or not targets:
            return IngestStageMetagenStepChunkScopeOutput(chunks=chunks)

        # 2. One strict schema + one rule block shared across every chunk (cacheable grammar).
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenPromptHelpers.field_rules(targets, self._field_types)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _one(chunk: Any) -> tuple[int, Any]:
            async with semaphore:
                return await self._generate_chunk(ctx, chunk, schema, rules)

        # 3. Fan out, then fold the per-chunk results back into the output.
        outcomes = await asyncio.gather(*[_one(c) for c in chunks])
        n_generated = sum(written for written, _ in outcomes)
        first = next((o for _, o in outcomes if o is not None), None)
        trace = MetagenCallHelpers.to_chain_trace(first) if first is not None else None

        self.logger.info(
            f"Metagen chunk-scope: generated={n_generated} chunks={len(chunks)} "
            f"targets={len(targets)}"
        )
        return IngestStageMetagenStepChunkScopeOutput(
            chunks=chunks, n_generated=n_generated, chain_trace=trace
        )

    async def _generate_chunk(
        self,
        ctx: IngestStageMetagenStepChunkScopeContext,
        chunk: Any,
        schema: dict[str, Any],
        rules: str,
    ) -> tuple[int, Any]:
        """
        Run one combined structured call for a chunk and write the result into ``derived_meta``.

        Args:
            ctx (IngestStageMetagenStepChunkScopeContext): The chain + the cache.
            chunk (Chunk): The chunk to enrich (mutated in place).
            schema (dict): The shared chunk-scope JSON schema.
            rules (str): The shared per-field rule block.

        Returns:
            tuple[int, Any]: (values written, ChainOutcome or None on a cache hit).
        """
        # 1. Build the per-chunk prompt from the chunk's heading breadcrumb + faithful text.
        heading = (getattr(chunk, "prov", {}) or {}).get("heading_path", "") or ""
        prompt = MetagenPromptHelpers.build_chunk_prompt(rules, heading, chunk.raw_text)
        data, outcome = await MetagenCallHelpers.call_cached(
            ctx.llm_chain, ctx.provider_cache, rules, prompt, schema, chunk.raw_text
        )

        # 2. Write only non-null generated values; the chunk keeps any prior derived_meta otherwise.
        written = 0
        for key, value in data.items():
            if value is not None:
                chunk.derived_meta[key] = value
                written += 1
        return written, outcome


__all__ = ["IngestStageMetagenStepChunkScope"]
