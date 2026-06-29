# ====== Code Summary ======
# S5bMetagenStage — the "metagen" stage: runs after S5, before S6, using an LLM chain to generate
# derived metadata for each chunk (chunk scope, one combined structured call per chunk) and/or for
# the document (document scope, one digest call). Chunk-scope values are written into
# chunk.derived_meta; document-scope values are returned as doc_fields for the orchestrator to merge
# into doc_meta. Every call is deduped via ProviderCallCache and bounded by a Semaphore + an upfront
# budget gate. An empty chain or empty targets is a complete no-op (full backward compatibility).

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import json
from typing import Any

# ====== Third-Party Library Imports ======
import blake3 as _blake3
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.pipeline.caches.fingerprint import compute_call_fingerprint
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.pipeline.bricks.chain import Chain

# ====== Local Project Imports ======
from .helpers import METAGEN_MAX_OUTPUT_TOKENS, MetagenHelpers
from .result import S5bResult
from .schema_builder import MetagenSchemaBuilder

# Provider-call cache capability + version tags for metagen calls.
_CAPABILITY = "metagen"
_PROVIDER_VERSION = "1"


class S5bMetagenStage(LoggerClass):
    """
    S5b — LLM-generated metadata stage (chunk-scope + document-scope).

    Targets are partitioned by scope. Chunk-scope targets share ONE strict JSON schema and are
    extracted with one combined ``generate_json`` call per chunk (run concurrently under a
    Semaphore); document-scope targets share another schema and produce a single call over a
    title + truncated-body digest. The provider chain is driven through ``Chain.call`` so each call
    is gated/escalated and traced; identical (rule-set, schema, content) calls dedupe via the
    cross-document ``ProviderCallCache``.
    """

    def __init__(
        self,
        llm_chain: Chain[Any, Any] | None,
        targets: list[Any],
        field_types: dict[str, MetaFieldSpec],
        provider_cache: ProviderCallCache,
        max_concurrency: int = 8,
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Wire the metagen stage.

        Args:
            llm_chain (Chain | None): Ordered LLM provider chain; None disables the stage.
            targets (list[MetaGenTarget]): Field bindings {field, prompt, scope}.
            field_types (dict[str, MetaFieldSpec]): Resolved type lookup for the generated fields
                this stage may populate (keyed by field name). Targets whose field is absent are
                ignored (the schema builder and prompt builders skip them).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            max_concurrency (int): Maximum concurrent chunk-scope calls.
            max_budget_usd (float): Estimated-cost cap per document (0 = unlimited).
        """
        LoggerClass.__init__(self)
        self._llm_chain = llm_chain
        self._targets = targets
        self._field_types = field_types
        self._provider_cache = provider_cache
        self._max_concurrency = max_concurrency
        self._max_budget_usd = max_budget_usd

    async def run(self, chunks: list[Any], ir: Any) -> S5bResult:
        """
        Generate chunk-scope and document-scope metadata for a document.

        Args:
            chunks (list[Chunk]): Contextualized chunks from S5 (mutated in place for chunk scope).
            ir (DocumentIR): The final IR (document-scope digest source).

        Returns:
            S5bResult: The same chunks (with ``derived_meta`` filled), the document-scope
                ``doc_fields``, counts, the estimated cost, and the chain traces.
        """
        # 1. No-op short-circuit — no provider or no bindings means nothing to generate.
        if self._llm_chain is None or not self._llm_chain.providers or not self._targets:
            return S5bResult(chunks=chunks)

        # 2. Partition targets by scope, keeping only those with a resolvable field type.
        chunk_targets = [t for t in self._targets if t.scope == "chunk" and t.field in self._field_types]
        doc_targets = [t for t in self._targets if t.scope == "document" and t.field in self._field_types]
        if not chunk_targets and not doc_targets:
            return S5bResult(chunks=chunks)

        # 3. Budget gate — degrade (leave empty) when the estimated spend exceeds the cap.
        est_cost = MetagenHelpers.estimate_total(
            chunks, chunk_targets, doc_targets, ir, self._field_types,
        )
        if self._max_budget_usd > 0 and est_cost > self._max_budget_usd:
            self.logger.warning(
                f"S5b metagen skipped: estimated cost ${est_cost:.4f} exceeds budget "
                f"${self._max_budget_usd:.4f} (doc_id={getattr(ir, 'doc_id', '?')}) — leaving fields empty."
            )
            return S5bResult(chunks=chunks, est_cost_usd=est_cost)

        # 4. Run both scopes, accumulating into the result.
        result = S5bResult(chunks=chunks, est_cost_usd=est_cost)
        if chunk_targets:
            await self._run_chunk_scope(chunks, chunk_targets, result)
        if doc_targets:
            await self._run_doc_scope(ir, doc_targets, result)

        self.logger.info(
            f"S5b done: doc_id={getattr(ir, 'doc_id', '?')} generated={result.n_generated} "
            f"chunk_targets={len(chunk_targets)} doc_targets={len(doc_targets)} est_cost=${est_cost:.4f}"
        )
        return result

    async def _run_chunk_scope(self, chunks: list[Any], targets: list[Any], result: S5bResult) -> None:
        """
        Generate chunk-scope metadata: one combined call per chunk under a concurrency Semaphore.

        Args:
            chunks (list[Chunk]): The chunks to enrich (mutated in place).
            targets (list[MetaGenTarget]): Resolvable chunk-scope targets.
            result (S5bResult): Accumulator (counts + traces).
        """
        # 1. One strict schema + one rule block shared across every chunk (cacheable grammar).
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenHelpers.field_rules(targets, self._field_types)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _one(chunk: Any) -> tuple[int, Any]:
            async with semaphore:
                return await self._generate_chunk(chunk, schema, rules)

        # 2. Fan out, then fold the per-chunk results back into the accumulator.
        outcomes = await asyncio.gather(*[_one(c) for c in chunks])
        for written, _ in outcomes:
            result.n_generated += written
        # One representative trace for the scope (the first real, non-cached call).
        first = next((o for _, o in outcomes if o is not None), None)
        if first is not None:
            result.chain_traces.append(MetagenHelpers.to_chain_trace(first))

    async def _run_doc_scope(self, ir: Any, targets: list[Any], result: S5bResult) -> None:
        """
        Generate document-scope metadata: one call over a title + truncated-body digest.

        Args:
            ir (DocumentIR): The final IR.
            targets (list[MetaGenTarget]): Resolvable document-scope targets.
            result (S5bResult): Accumulator (doc_fields + counts + traces).
        """
        schema = MetagenSchemaBuilder.build_json_schema(targets, self._field_types)
        rules = MetagenHelpers.field_rules(targets, self._field_types)
        body = MetagenHelpers.document_digest(ir)
        prompt = MetagenHelpers.build_doc_prompt(rules, getattr(ir, "title", ""), body)

        data, outcome = await self._call_cached(rules, prompt, schema, body)
        for key, value in data.items():
            if value is not None:
                result.doc_fields[key] = value
                result.n_generated += 1
        if outcome is not None:
            result.chain_traces.append(MetagenHelpers.to_chain_trace(outcome))

    async def _generate_chunk(self, chunk: Any, schema: dict[str, Any], rules: str) -> tuple[int, Any]:
        """
        Run one combined structured call for a chunk and write the result into ``derived_meta``.

        Args:
            chunk (Chunk): The chunk to enrich (mutated in place).
            schema (dict): The shared chunk-scope JSON schema.
            rules (str): The shared per-field rule block.

        Returns:
            tuple[int, Any]: (values written, ChainOutcome or None on cache hit).
        """
        heading = (getattr(chunk, "prov", {}) or {}).get("heading_path", "") or ""
        prompt = MetagenHelpers.build_chunk_prompt(rules, heading, chunk.raw_text)
        data, outcome = await self._call_cached(rules, prompt, schema, chunk.raw_text)

        # Write only non-null generated values; the chunk keeps any prior derived_meta otherwise.
        written = 0
        for key, value in data.items():
            if value is not None:
                chunk.derived_meta[key] = value
                written += 1
        return written, outcome

    async def _call_cached(
        self,
        rules: str,
        prompt: str,
        schema: dict[str, Any],
        content_text: str,
    ) -> tuple[dict[str, Any], Any]:
        """
        Resolve one generate_json call through the provider-call cache, then the chain.

        The cache key is the (rule-set, schema) prompt signature × the blake3 of the content text,
        so editing a prompt or a field type recomputes while identical (rules, schema, text) inputs
        dedupe across documents.

        Args:
            rules (str): The rule block (part of the cache params).
            prompt (str): The full prompt sent to the LLM.
            schema (dict): The strict JSON schema (part of the cache params).
            content_text (str): The content addressed by the cache (chunk text or doc digest).

        Returns:
            tuple[dict, Any]: (parsed object, ChainOutcome or None on a cache hit).
        """
        # 1. Compute the content-addressed cache key and try the cache.
        content_hash = _blake3.blake3(content_text.encode("utf-8")).hexdigest()
        call_fp = compute_call_fingerprint(
            capability=_CAPABILITY,
            provider_id=self._llm_chain.first_provider_name,
            provider_version=_PROVIDER_VERSION,
            params={"rules": rules, "schema": schema},
            content_hash=content_hash,
        )
        cached = await self._provider_cache.get(call_fp)
        if cached is not None:
            try:
                return json.loads(cached), None
            except (json.JSONDecodeError, ValueError):
                pass  # Corrupt cache entry → fall through to a fresh call.

        # 2. Miss → run the chain (each provider's generate_json self-degrades to {} on failure).
        outcome = await self._llm_chain.call(
            lambda p: p.generate_json(prompt, schema, max_tokens=METAGEN_MAX_OUTPUT_TOKENS, temperature=0.0)
        )
        data = outcome.result if isinstance(outcome.result, dict) else {}

        # 3. Persist a non-empty result for cross-document reuse.
        if data:
            await self._provider_cache.put(
                call_fp, _CAPABILITY, self._llm_chain.first_provider_name,
                _PROVIDER_VERSION, content_hash, json.dumps(data),
            )
        return data, outcome


# ------------------- Public API ------------------- #
__all__ = ["S5bMetagenStage"]
