# ====== Code Summary ======
# CallKeyHelpers - resolves a chain's first provider into the (provider_id, provider_version,
# call_fp) triple used to consult and persist the ProviderCallCache. Shared by every enrich
# capability runner (classifier / OCR / VLM) so the cache-key mechanics live in one place. The
# fingerprint is content-based (capability + provider id/version + params + crop hash), so it is
# independent of iteration order - the per-capability passes produce the same keys as the legacy
# per-figure path.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.caches import ProviderCallCache
from common_libs.pipelines.capabilities.chain import Chain


class CallKeyHelpers:
    """
    Static helper that derives provider-call cache keys from a chain's first provider.

    The first provider drives the cache key because it is the one that *would* run on a cache miss;
    escalation to later providers only happens when the first one fails the gate.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation - this is a static-only helper class."""
        raise TypeError("CallKeyHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve(
        chain: "Chain[Any, Any]",
        capability: str,
        default_id: str,
        params: dict[str, Any],
        content_hash: str,
    ) -> tuple[Any, str, str, str] | None:
        """
        Resolve the first provider and compute its provider-call fingerprint.

        Args:
            chain (Chain[Any, Any]): The capability chain (may be empty).
            capability (str): Capability label (``"classifier"`` / ``"ocr"`` / ``"vlm"``).
            default_id (str): Fallback provider id when the provider exposes no ``name``.
            params (dict[str, Any]): Call parameters folded into the fingerprint.
            content_hash (str): SHA-256 hex digest of the crop bytes.

        Returns:
            tuple[Any, str, str, str] | None: ``(first_provider, provider_id, provider_version,
                call_fp)`` or None when the chain has no providers.
        """
        first_provider = chain.providers[0] if chain.providers else None
        if first_provider is None:
            return None
        provider_id = getattr(first_provider, "name", default_id)
        provider_version = getattr(first_provider, "version", "0")
        call_fp = ProviderCallCache.compute_key(
            capability=capability,
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=content_hash,
        )
        return first_provider, provider_id, provider_version, call_fp

    @staticmethod
    async def persist(
        provider_cache: ProviderCallCache,
        call_fp: str,
        capability: str,
        provider_id: str,
        provider_version: str,
        content_hash: str,
        result_json: str,
    ) -> None:
        """
        Persist a provider-call result so an identical future crop is a cache hit.

        Args:
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            call_fp (str): Provider-call fingerprint computed by ``resolve``.
            capability (str): Capability label.
            provider_id (str): Provider id that produced the result.
            provider_version (str): Provider version.
            content_hash (str): SHA-256 hex digest of the crop bytes.
            result_json (str): Serialized result payload.
        """
        await provider_cache.put(
            call_fp=call_fp,
            capability=capability,
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=content_hash,
            result_json=result_json,
        )


__all__ = ["CallKeyHelpers"]
