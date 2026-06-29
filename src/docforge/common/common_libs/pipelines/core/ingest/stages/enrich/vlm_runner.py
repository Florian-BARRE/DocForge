# ====== Code Summary ======
# VlmRunner - runs the enrich VLM capability through the ProviderCallCache. Kept separate from
# CacheRunner because VLM is the only capability that resolves a chart-to-data schema from the
# concrete provider type (via a late import to avoid a circular dependency). It returns the full
# VlmResult (description + raw structured output) so the chart step can extract the data table from
# the same single VLM call - the chart-to-data is a PARAMETER of this call (it changes the requested
# schema and the cache key), never a second provider call.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines.capabilities.caches import ProviderCallCache
from common_libs.pipelines.capabilities.chain import Chain
from common_libs.providers import VlmResult

# ====== Local Project Imports ======
from .call_key import CallKeyHelpers
from .trace_builder import TraceHelpers


class VlmRunner:
    """
    Static helper that runs the VLM capability behind the provider-call cache.

    Same contract as the other enrich capability runners: derive a fingerprint, consult the cache
    (synthetic trace on hit), else invoke the chain and persist the result.
    """

    logger = loggerplusplus.bind(identifier="VlmRunner")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation - this is a static-only helper class."""
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
    ) -> tuple[VlmResult | None, ChainTrace, bool]:
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
            tuple: ``(VlmResult | None, ChainTrace, was_cache_hit)``.
        """
        # 1. Guard + resolve provider/cache key.
        if vlm_chain is None:
            return None, TraceHelpers.skip("vlm", "no chain"), False
        params = {"grounding": bool(ocr_text), "chart_schema": use_chart_schema}
        resolved = CallKeyHelpers.resolve(vlm_chain, "vlm", "vlm", params, crop_hash)
        if resolved is None:
            return None, TraceHelpers.skip("vlm", "no provider"), False
        first_provider, provider_id, provider_version, call_fp = resolved

        # 2. Check cache.
        cached_raw = await provider_cache.get(call_fp)
        if cached_raw is not None:
            cls.logger.debug(f"VlmRunner: VLM cache HIT fp={call_fp[:12]}")
            return (
                VlmResult.model_validate_json(cached_raw),
                TraceHelpers.cache_hit("vlm", provider_id, call_fp),
                True,
            )

        # 3. Resolve chart schema from provider type - late import avoids a circular dep.
        from common_libs.providers.vlm import OpenAICompatVlmProvider  # noqa: PLC0415

        schema = (
            OpenAICompatVlmProvider.chart_schema()
            if use_chart_schema and isinstance(first_provider, OpenAICompatVlmProvider)
            else None
        )

        # 4. Cache miss - invoke the chain.
        outcome = await vlm_chain.call(
            lambda p: p.describe(crop_bytes, grounding=ocr_text, schema=schema)
        )
        trace = TraceHelpers.from_outcome("vlm", outcome)
        if outcome.result is None:
            return None, trace, False

        # 5. Persist result for deduplication.
        await CallKeyHelpers.persist(
            provider_cache, call_fp, "vlm", provider_id, provider_version,
            crop_hash, outcome.result.model_dump_json(),
        )
        return outcome.result, trace, False


__all__ = ["VlmRunner"]
