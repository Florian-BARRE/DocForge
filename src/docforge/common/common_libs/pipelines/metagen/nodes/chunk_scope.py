# ====== Code Summary ======
# MetagenChunkScope — the chunk-scope metagen node. It generates one combined strict JSON call per
# chunk (run concurrently under a Semaphore), writing the non-null generated values into each
# ``chunk.derived_meta`` in place. All chunk-scope targets share one schema + one rule block (cacheable
# grammar); every call deduplicates through the injected provider cache. When the budget gate says not
# to proceed, the node passes the chunks through unchanged (full no-op).

# ====== Standard Library Imports ======
import asyncio
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget
from common_libs.domain import ChainTrace, Chunk, MetaFieldSpec
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


class MetagenChunkScopeInput(NodeInput):
    """
    Input of the chunk-scope node.

    Attributes:
        chunks (list[Chunk]): The document's chunks (from the metagen stage input).
        proceed (bool): The budget-gate decision (from the budget-gate node).
    """

    chunks: Annotated[list[Chunk], FromGroupInput()]
    proceed: Annotated[bool, FromNode("budget_gate", "proceed")]


class MetagenChunkScopeOutput(NodeOutput):
    """
    Output of the chunk-scope node.

    Attributes:
        chunks (list[Chunk]): The same chunks, with chunk-scope generated values written into each
            ``chunk.derived_meta`` (mutated in place).
        n_generated (int): Count of chunk-scope generated values written.
        chain_trace (ChainTrace | None): One representative trace (first real, non-cached call), or
            None when nothing ran.
    """

    chunks: list[Chunk]
    n_generated: int = 0
    chain_trace: ChainTrace | None = None


class MetagenChunkScope(ActionNode):
    """
    Generate chunk-scope metadata: one combined structured call per chunk under a Semaphore.

    Reads the chunks + the budget-gate proceed flag; writes the same chunks (with ``derived_meta``
    filled), the count generated, and one representative chain trace.
    """

    Input = MetagenChunkScopeInput
    Output = MetagenChunkScopeOutput

    def __init__(
        self,
        node_id: str,
        targets: list[MetaGenTarget],
        field_types: dict[str, MetaFieldSpec],
        max_concurrency: int = 8,
    ) -> None:
        """
        Wire the chunk-scope node with its assembly-time config.

        Args:
            node_id (str): The node's id (unique among its siblings).
            targets (list[MetaGenTarget]): Field bindings ``{field, prompt, scope}``.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup keyed by field name.
            max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
        """
        super().__init__(node_id)
        self._targets = targets
        self._field_types = field_types
        self._max_concurrency = max_concurrency

    async def execute(self, ctx: Context) -> MetagenChunkScopeOutput:
        """
        Generate chunk-scope metadata, or pass the chunks through when not proceeding.

        Args:
            ctx (Context): The resolved input + the injected ``llm_chain`` + ``provider_cache``.

        Returns:
            MetagenChunkScopeOutput: The chunks + count generated + representative trace.
        """
        # 1. No-op passthrough when the budget gate declined, or when there is no chunk-scope target.
        chunks = ctx.input.chunks
        targets = MetagenPromptHelpers.scope_targets(self._targets, self._field_types, "chunk")
        if not ctx.input.proceed or not targets:
            return MetagenChunkScopeOutput(chunks=chunks)

        # 2. One strict schema + one rule block shared across every chunk (cacheable grammar).
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenPromptHelpers.field_rules(targets, self._field_types)
        semaphore = asyncio.Semaphore(self._max_concurrency)
        chain = ctx.service("llm_chain")
        provider_cache = ctx.service("provider_cache")

        async def _one(chunk: Any) -> tuple[int, Any]:
            async with semaphore:
                return await self._generate_chunk(chain, provider_cache, chunk, schema, rules)

        # 3. Fan out, then fold the per-chunk results back into the output.
        outcomes = await asyncio.gather(*[_one(c) for c in chunks])
        n_generated = sum(written for written, _ in outcomes)
        first = next((o for _, o in outcomes if o is not None), None)
        trace = MetagenCallHelpers.to_chain_trace(first) if first is not None else None

        self.logger.info(
            f"Metagen chunk-scope: generated={n_generated} chunks={len(chunks)} "
            f"targets={len(targets)}"
        )
        return MetagenChunkScopeOutput(chunks=chunks, n_generated=n_generated, chain_trace=trace)

    async def _generate_chunk(
        self,
        chain: Any,
        provider_cache: Any,
        chunk: Any,
        schema: dict[str, Any],
        rules: str,
    ) -> tuple[int, Any]:
        """
        Run one combined structured call for a chunk and write the result into ``derived_meta``.

        Args:
            chain (Chain): The injected LLM provider chain.
            provider_cache (ProviderCallCache): The cross-document provider-call cache.
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
            chain, provider_cache, rules, prompt, schema, chunk.raw_text
        )

        # 2. Write only non-null generated values; the chunk keeps any prior derived_meta otherwise.
        written = 0
        for key, value in data.items():
            if value is not None:
                chunk.derived_meta[key] = value
                written += 1
        return written, outcome


__all__ = ["MetagenChunkScope", "MetagenChunkScopeInput", "MetagenChunkScopeOutput"]
