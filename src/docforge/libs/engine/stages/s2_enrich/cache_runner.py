# ====== Code Summary ======
# CacheRunner — async helpers that wrap each S2 capability (classifier, OCR, VLM)
# behind the ProviderCallCache.  Each helper returns a (result, cost, trace, was_hit) tuple
# so the caller (S2EnrichStage.run) never needs to know the cache key mechanics.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.core.ir.models import ChainTrace, FigureKind
from libs.engine.provider_cache import ProviderCallCache
from libs.capabilities.chain import Chain
from libs.capabilities.classifier.base import ClassificationResult
from libs.capabilities.interfaces import OcrHint, OcrResult, VlmResult

# ====== Local Project Imports ======
from .trace_helpers import TraceHelpers


class CacheRunner:
    """
    Async helpers that execute each S2 capability through the ``ProviderCallCache``.

    Each ``run_*`` class-method follows the same contract:

    1. Derive a provider-call fingerprint from the capability name, provider id/version,
       call params, and the crop content-hash.
    2. Consult the cache — if hit, return a synthetic trace and skip the chain.
    3. On miss, invoke the chain, persist the result, and return the real trace.

    This is a static-only class — all methods are ``@classmethod`` so they can log.
    """

    logger = loggerplusplus.bind(identifier="CacheRunner")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @classmethod
    async def run_classify(
        cls,
        classifier_chain: "Chain[Any, Any]",
        provider_cache: ProviderCallCache,
        crop_bytes: bytes,
        crop_hash: str,
    ) -> tuple[ClassificationResult | None, ChainTrace, bool]:
        """
        Classify a figure via the chain, dedup-ing across identical crops.

        The classification result is keyed by ``crop_hash`` so a repeated logo or
        header runs the classifier model exactly once across every document.

        Args:
            classifier_chain (Chain[Any, Any]): Configured classifier chain (non-empty).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            crop_bytes (bytes): Raw figure crop image bytes.
            crop_hash (str): SHA-256 hex digest of ``crop_bytes``.

        Returns:
            tuple: ``(ClassificationResult | None, ChainTrace, was_cache_hit)``.
        """
        # 1. Resolve the first provider for fingerprint computation.
        first_provider = (
            classifier_chain.providers[0] if classifier_chain.providers else None
        )
        if first_provider is None:
            return None, TraceHelpers.skip("classifier", "no provider"), False

        provider_id = getattr(first_provider, "name", "classifier")
        provider_version = getattr(first_provider, "version", "0")
        call_fp = ProviderCallCache.compute_key(
            capability="classifier",
            provider_id=provider_id,
            provider_version=provider_version,
            params={},
            content_hash=crop_hash,
        )

        # 2. Check cache — ClassificationResult round-trips via a minimal JSON dict.
        cached_raw = await provider_cache.get(call_fp)
        if cached_raw is not None:
            cls.logger.debug(f"CacheRunner: classifier cache HIT fp={call_fp[:12]}…")
            data = json.loads(cached_raw)
            return (
                ClassificationResult(
                    kind=FigureKind(data["kind"]),
                    confidence=float(data["confidence"]),
                ),
                TraceHelpers.cache_hit("classifier", provider_id, call_fp),
                True,
            )

        # 3. Cache miss — invoke the chain.
        outcome = await classifier_chain.call(lambda p: p.classify(crop_bytes))
        trace = TraceHelpers.from_outcome("classifier", outcome)
        if outcome.result is None:
            return None, trace, False

        # 4. Persist for next identical crop.
        result_json = (
            f'{{"kind": "{outcome.result.kind.value}", '
            f'"confidence": {outcome.result.confidence}}}'
        )
        await provider_cache.put(
            call_fp=call_fp,
            capability="classifier",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=result_json,
            cost=0.0,
        )
        return outcome.result, trace, False

    @classmethod
    async def run_ocr(
        cls,
        ocr_chain: "Chain[Any, Any] | None",
        provider_cache: ProviderCallCache,
        crop_bytes: bytes,
        crop_hash: str,
        doc_language: str,
    ) -> tuple[OcrResult | None, float, ChainTrace, bool]:
        """
        Run OCR via the chain, consulting the provider-call cache first.

        Args:
            ocr_chain (Chain[Any, Any] | None): OCR chain; None disables OCR.
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            crop_bytes (bytes): Raw figure crop image bytes.
            crop_hash (str): SHA-256 hex digest of ``crop_bytes``.
            doc_language (str): Document language hint (ISO 639-1, e.g. ``"en"``).

        Returns:
            tuple: ``(OcrResult | None, cost_incurred, ChainTrace, was_cache_hit)``.
                A cache hit emits a synthetic trace whose ``final_provider`` is
                ``"cache"`` so block-level lineage shows "served from provider-call cache".
        """
        # 1. Guard — no chain configured.
        if ocr_chain is None:
            return None, 0.0, TraceHelpers.skip("ocr", "no chain"), False

        first_provider = ocr_chain.providers[0] if ocr_chain.providers else None
        if first_provider is None:
            return None, 0.0, TraceHelpers.skip("ocr", "no provider"), False

        provider_id = getattr(first_provider, "name", "ocr")
        provider_version = getattr(first_provider, "version", "0")
        params = {"language": doc_language}
        call_fp = ProviderCallCache.compute_key(
            capability="ocr",
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=crop_hash,
        )

        # 2. Check cache.
        cached_raw = await provider_cache.get(call_fp)
        if cached_raw is not None:
            cls.logger.debug(f"CacheRunner: OCR cache HIT fp={call_fp[:12]}…")
            return (
                OcrResult.model_validate_json(cached_raw),
                0.0,
                TraceHelpers.cache_hit("ocr", provider_id, call_fp),
                True,
            )

        # 3. Cache miss — invoke the chain.
        hint = OcrHint(language=doc_language)
        outcome = await ocr_chain.call(lambda p: p.extract(crop_bytes, hint))
        trace = TraceHelpers.from_outcome("ocr", outcome)

        if outcome.result is None:
            return None, 0.0, trace, False

        cost = getattr(first_provider, "cost_per_page", 0.0)

        # 4. Persist result for deduplication.
        await provider_cache.put(
            call_fp=call_fp,
            capability="ocr",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=outcome.result.model_dump_json(),
            cost=cost,
        )
        return outcome.result, cost, trace, False

    @classmethod
    async def run_vlm(
        cls,
        vlm_chain: "Chain[Any, Any] | None",
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
        # 1. Guard — no chain configured.
        if vlm_chain is None:
            return None, 0.0, TraceHelpers.skip("vlm", "no chain"), False

        first_provider = vlm_chain.providers[0] if vlm_chain.providers else None
        if first_provider is None:
            return None, 0.0, TraceHelpers.skip("vlm", "no provider"), False

        provider_id = getattr(first_provider, "name", "vlm")
        provider_version = getattr(first_provider, "version", "0")
        params = {"grounding": bool(ocr_text), "chart_schema": use_chart_schema}
        call_fp = ProviderCallCache.compute_key(
            capability="vlm",
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=crop_hash,
        )

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
        await provider_cache.put(
            call_fp=call_fp,
            capability="vlm",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=outcome.result.model_dump_json(),
            cost=cost,
        )
        return outcome.result, cost, trace, False


# ------------------- Public API ------------------- #
__all__ = ["CacheRunner"]
