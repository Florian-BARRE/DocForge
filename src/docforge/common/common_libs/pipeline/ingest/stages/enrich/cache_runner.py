# ====== Code Summary ======
# CacheRunner — async helpers that wrap the classifier and OCR capabilities behind the
# ProviderCallCache. Each helper returns a (result, trace, was_hit) tuple so the caller (the
# classify / OCR steps) never needs to know the cache-key mechanics. Cache-key resolution is
# delegated to CallKeyHelpers; the VLM capability lives in VlmRunner (it resolves a chart-to-data
# schema from the concrete provider type). The cache keys are content-based, so running these per
# capability over all figures yields the same hit/miss pattern as the legacy per-figure path.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from common_libs.pipeline.bricks.chain import Chain
from common_libs.providers.classifier.base import ClassificationResult
from common_libs.providers.interfaces import OcrHint, OcrResult

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainTrace, FigureKind
from common_libs.pipeline.caches.provider_cache import ProviderCallCache

# ====== Local Project Imports ======
from .call_key import CallKeyHelpers
from .trace_helpers import TraceHelpers


class CacheRunner:
    """
    Async helpers that execute the classifier / OCR capabilities through the ``ProviderCallCache``.

    Each ``run_*`` class-method follows the same contract:

    1. Derive a provider-call fingerprint (via CallKeyHelpers) from the capability name,
       provider id/version, call params, and the crop content-hash.
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
        classifier_chain: Chain[Any, Any],
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
        # 1. Resolve provider + cache key.
        resolved = CallKeyHelpers.resolve(
            classifier_chain, "classifier", "classifier", {}, crop_hash,
        )
        if resolved is None:
            return None, TraceHelpers.skip("classifier", "no provider"), False
        _first, provider_id, provider_version, call_fp = resolved

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
        await CallKeyHelpers.persist(
            provider_cache, call_fp, "classifier", provider_id, provider_version,
            crop_hash, result_json,
        )
        return outcome.result, trace, False

    @classmethod
    async def run_ocr(
        cls,
        ocr_chain: Chain[Any, Any] | None,
        provider_cache: ProviderCallCache,
        crop_bytes: bytes,
        crop_hash: str,
        doc_language: str,
    ) -> tuple[OcrResult | None, ChainTrace, bool]:
        """
        Run OCR via the chain, consulting the provider-call cache first.

        A cache hit emits a synthetic trace whose ``final_provider`` is ``"provider_cache"``
        so block-level lineage shows "served from provider-call cache".

        Args:
            ocr_chain (Chain[Any, Any] | None): OCR chain; None disables OCR.
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            crop_bytes (bytes): Raw figure crop image bytes.
            crop_hash (str): SHA-256 hex digest of ``crop_bytes``.
            doc_language (str): Document language hint (ISO 639-1, e.g. ``"en"``).

        Returns:
            tuple: ``(OcrResult | None, ChainTrace, was_cache_hit)``.
        """
        # 1. Guard + resolve provider/cache key.
        if ocr_chain is None:
            return None, TraceHelpers.skip("ocr", "no chain"), False
        resolved = CallKeyHelpers.resolve(
            ocr_chain, "ocr", "ocr", {"language": doc_language}, crop_hash,
        )
        if resolved is None:
            return None, TraceHelpers.skip("ocr", "no provider"), False
        _first_provider, provider_id, provider_version, call_fp = resolved

        # 2. Check cache.
        cached_raw = await provider_cache.get(call_fp)
        if cached_raw is not None:
            cls.logger.debug(f"CacheRunner: OCR cache HIT fp={call_fp[:12]}…")
            return (
                OcrResult.model_validate_json(cached_raw),
                TraceHelpers.cache_hit("ocr", provider_id, call_fp),
                True,
            )

        # 3. Cache miss — invoke the chain.
        hint = OcrHint(language=doc_language)
        outcome = await ocr_chain.call(lambda p: p.extract(crop_bytes, hint))
        trace = TraceHelpers.from_outcome("ocr", outcome)
        if outcome.result is None:
            return None, trace, False

        # 4. Persist result for deduplication.
        await CallKeyHelpers.persist(
            provider_cache, call_fp, "ocr", provider_id, provider_version,
            crop_hash, outcome.result.model_dump_json(),
        )
        return outcome.result, trace, False


# ------------------- Public API ------------------- #
__all__ = ["CacheRunner"]
