# ====== Code Summary ======
# VlmRunner — runs the S2 VLM capability through the ProviderCallCache.  Kept separate from
# CacheRunner because VLM is the only capability that resolves a chart-to-data schema from
# the concrete provider type (via a late import to avoid a circular dependency).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from libs.capabilities.chain import Chain
from libs.capabilities.interfaces import VlmResult

# ====== Internal Project Imports ======
from libs.core.ir.models import ChainTrace
from libs.engine.provider_cache import ProviderCallCache

# ====== Local Project Imports ======
from .call_key import CallKeyHelpers
from .trace_helpers import TraceHelpers


class VlmRunner:
    """
    Static helper that runs the VLM capability behind the provider-call cache.

    Same contract as the other S2 capability runners: derive a fingerprint, consult the
    cache (synthetic trace on hit), else invoke the chain and persist the result.
    """

    logger = loggerplusplus.bind(identifier="CacheRunner")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @classmethod
    async def run_vlm(
        cls,
        vlm_chain: Chain[Any, Any] | None,
        provider_cache: ProviderCallCache,
        crop_bytes: bytes,
        crop_hash: str,
        ocr_text: str | None,
        use_chart_schema: bool,
    ) -> tuple[VlmResult | None, float, ChainTrace, bool]:
        """
        Run VLM description via the chain, consulting the provider-call cache first.

        Args:
            vlm_chain (Chain[Any, Any] | None): VLM chain; None disables VLM.
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            crop_bytes (bytes): Raw figure crop image bytes.
            crop_hash (str): SHA-256 hex digest of ``crop_bytes``.
            ocr_text (str | None): Grounding text from OCR (passed to VLM as context).
            use_chart_schema (bool): Whether to request structured chart-to-data output.

        Returns:
            tuple: ``(VlmResult | None, cost_incurred, ChainTrace, was_cache_hit)``.
        """
        # 1. Guard + resolve provider/cache key.
        if vlm_chain is None:
            return None, 0.0, TraceHelpers.skip("vlm", "no chain"), False
        params = {"grounding": bool(ocr_text), "chart_schema": use_chart_schema}
        resolved = CallKeyHelpers.resolve(vlm_chain, "vlm", "vlm", params, crop_hash)
        if resolved is None:
            return None, 0.0, TraceHelpers.skip("vlm", "no provider"), False
        first_provider, provider_id, provider_version, call_fp = resolved

        # 2. Check cache.
        cached_raw = await provider_cache.get(call_fp)
        if cached_raw is not None:
            cls.logger.debug(f"CacheRunner: VLM cache HIT fp={call_fp[:12]}…")
            return (
                VlmResult.model_validate_json(cached_raw),
                0.0,
                TraceHelpers.cache_hit("vlm", provider_id, call_fp),
                True,
            )

        # 3. Resolve chart schema from provider type — late import avoids a circular dep.
        from libs.capabilities.vlm import OpenAICompatVlmProvider  # noqa: PLC0415

        schema = (
            OpenAICompatVlmProvider.chart_schema()
            if use_chart_schema and isinstance(first_provider, OpenAICompatVlmProvider)
            else None
        )

        # 4. Cache miss — invoke the chain.
        outcome = await vlm_chain.call(
            lambda p: p.describe(crop_bytes, grounding=ocr_text, schema=schema)
        )
        trace = TraceHelpers.from_outcome("vlm", outcome)
        if outcome.result is None:
            return None, 0.0, trace, False

        cost = getattr(first_provider, "cost_per_call", 0.0)

        # 5. Persist result for deduplication.
        await CallKeyHelpers.persist(
            provider_cache, call_fp, "vlm", provider_id, provider_version,
            crop_hash, outcome.result.model_dump_json(), cost,
        )
        return outcome.result, cost, trace, False


# ------------------- Public API ------------------- #
__all__ = ["VlmRunner"]
