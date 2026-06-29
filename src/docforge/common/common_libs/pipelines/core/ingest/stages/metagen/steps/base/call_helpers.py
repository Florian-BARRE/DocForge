# ====== Code Summary ======
# MetagenCallHelpers — static helpers wrapping ONE LLM generate_json call for the metagen scope steps.
# It resolves a call through the cross-document ProviderCallCache first (keyed by the rule-set/schema
# prompt signature times the blake3 of the content text), then runs the injected LLM chain on a miss,
# persisting non-empty results for cross-document reuse. It also converts a ChainOutcome into a domain
# ChainTrace stamped under stage="metagen" for the orchestrator's lineage flush.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import blake3 as _blake3

# ====== Internal Project Imports ======
from common_libs.domain import ChainAttemptIR, ChainTrace
from common_libs.pipelines.bricks.caches import compute_call_fingerprint
from common_libs.pipelines.bricks.chain import Chain, ChainHelpers

# ====== Local Project Imports ======
from .prompts import METAGEN_MAX_OUTPUT_TOKENS

# Provider-call cache capability + version tags for metagen calls.
_CAPABILITY = "metagen"
_PROVIDER_VERSION = "1"


class MetagenCallHelpers:
    """
    Static helpers for the metagen scope steps (cached LLM call + trace conversion).

    No instance state of its own — the LLM chain and provider cache are passed in per call so the
    same logic serves both the chunk-scope and document-scope steps.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("MetagenCallHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def call_cached(
        cls,
        chain: Chain[Any, Any],
        provider_cache: Any,
        rules: str,
        prompt: str,
        schema: dict[str, Any],
        content_text: str,
    ) -> tuple[dict[str, Any], Any]:
        """
        Resolve one generate_json call through the provider-call cache, then the chain.

        The cache key is the (rule-set, schema) prompt signature times the blake3 of the content
        text, so editing a prompt or a field type recomputes while identical (rules, schema, text)
        inputs dedupe across documents.

        Args:
            chain (Chain): The injected LLM provider chain.
            provider_cache (ProviderCallCache): The cross-document provider-call cache.
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
            provider_id=chain.first_provider_name,
            provider_version=_PROVIDER_VERSION,
            params={"rules": rules, "schema": schema},
            content_hash=content_hash,
        )
        cached = await provider_cache.get(call_fp)
        if cached is not None:
            try:
                return json.loads(cached), None
            except (json.JSONDecodeError, ValueError):
                pass  # Corrupt cache entry -> fall through to a fresh call.

        # 2. Miss -> run the chain (each provider's generate_json self-degrades to {} on failure).
        outcome = await chain.call(
            lambda p: p.generate_json(
                prompt, schema, max_tokens=METAGEN_MAX_OUTPUT_TOKENS, temperature=0.0
            )
        )
        data = outcome.result if isinstance(outcome.result, dict) else {}

        # 3. Persist a non-empty result for cross-document reuse.
        if data:
            await provider_cache.put(
                call_fp,
                _CAPABILITY,
                chain.first_provider_name,
                _PROVIDER_VERSION,
                content_hash,
                json.dumps(data),
            )
        return data, outcome

    @staticmethod
    def to_chain_trace(outcome: Any) -> ChainTrace:
        """
        Convert a ChainOutcome into a ChainTrace IR record for the metagen stage.

        Args:
            outcome (ChainOutcome): The chain invocation record.

        Returns:
            ChainTrace: The serialisable trace stamped under ``stage="metagen"``.
        """
        attempts = [
            ChainAttemptIR(**d) for d in ChainHelpers.chain_outcome_to_attempt_dicts(outcome)
        ]
        return ChainTrace(
            stage="metagen",
            attempts=attempts,
            final_provider=outcome.final_provider,
            degraded=outcome.degraded,
            gate_tripped=ChainHelpers.gate_tripped(outcome) if outcome.degraded else None,
        )


__all__ = ["MetagenCallHelpers"]
