# ====== Code Summary ======
# Merkle-DAG fingerprinting for the P2 stage engine.
# Each pipeline node fingerprint encodes: node type, code version, canonical params,
# and the ordered list of upstream input fingerprints.  Any change invalidates the cache.
#
# FingerprintHelpers wraps the two computation functions as a static-only class.
# Module-level shims preserve the original import path for all existing callers.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
import blake3 as _blake3


class FingerprintHelpers:
    """
    Static helper wrapping blake3 Merkle-DAG fingerprint computation.

    Two distinct fingerprint families:
    - ``compute_fingerprint``: per-node Merkle-DAG key (node type + code version + params + inputs).
    - ``compute_call_fingerprint``: provider-call cache key (capability + provider + content hash).

    This is a static-only class — instantiation is intentionally blocked.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — all methods are static."""
        raise TypeError("FingerprintHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def compute_fingerprint(
        node_type: str,
        code_version: str,
        params: dict[str, Any],
        input_fingerprints: list[str],
    ) -> str:
        """
        Compute a deterministic Merkle-DAG fingerprint for a pipeline node.

        The fingerprint encodes: node type, code version, canonical JSON of params,
        and the ordered list of upstream input fingerprints.  Any change to any field
        produces a different fingerprint, triggering cache invalidation downstream.

        Args:
            node_type (str): Logical node identifier (e.g. ``"ingest"``, ``"parse"``).
            code_version (str): Node implementation version (e.g. ``"1.0"``).
            params (dict): Node configuration parameters (must be JSON-serialisable).
            input_fingerprints (list[str]): Fingerprints of upstream nodes in dependency order.
                Order is preserved — DAG edges are directed, not a set.

        Returns:
            str: 64-character hex blake3 digest.
        """
        # 1. Canonical JSON: sort_keys ensures stability regardless of dict insertion order
        canonical = json.dumps(
            {
                "node_type": node_type,
                "code_version": code_version,
                "params": params,
                "inputs": input_fingerprints,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        # 2. Compute blake3 hash over the canonical payload
        return _blake3.blake3(canonical).hexdigest()

    @staticmethod
    def compute_call_fingerprint(
        capability: str,
        provider_id: str,
        provider_version: str,
        params: dict[str, Any],
        content_hash: str,
    ) -> str:
        """
        Compute a provider-call cache key from provider identity and content address.

        Used by ProviderCallCache to deduplicate identical API calls across documents.
        The key encodes all dimensions that determine the output — same inputs → same key.

        Args:
            capability (str): Provider capability (e.g. ``"ocr"``, ``"embed"``, ``"vlm"``).
            provider_id (str): Provider identifier (e.g. ``"mistral_ocr_api"``).
            provider_version (str): Provider version string (e.g. ``"2024-12"``).
            params (dict): Call parameters (prompt, resolution, language, …).
            content_hash (str): Blake3 hash of the content being processed.

        Returns:
            str: 64-character hex blake3 digest.
        """
        # 1. Canonical JSON of the provider call descriptor
        canonical = json.dumps(
            {
                "capability": capability,
                "provider_id": provider_id,
                "provider_version": provider_version,
                "params": params,
                "content_hash": content_hash,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        # 2. Compute blake3 hash
        return _blake3.blake3(canonical).hexdigest()


# ─── Module-level shims ───────────────────────────────────────────────────────
# Preserve backward-compatible import: ``from libs.pipeline.caches.fingerprint import compute_fingerprint``
# All callers continue to work without modification.

def compute_fingerprint(
    node_type: str,
    code_version: str,
    params: dict[str, Any],
    input_fingerprints: list[str],
) -> str:
    """
    Module-level shim for ``FingerprintHelpers.compute_fingerprint``.

    Args:
        node_type (str): Logical node identifier.
        code_version (str): Node implementation version.
        params (dict): Node configuration parameters.
        input_fingerprints (list[str]): Upstream node fingerprints.

    Returns:
        str: 64-character hex blake3 digest.
    """
    return FingerprintHelpers.compute_fingerprint(node_type, code_version, params, input_fingerprints)


def compute_call_fingerprint(
    capability: str,
    provider_id: str,
    provider_version: str,
    params: dict[str, Any],
    content_hash: str,
) -> str:
    """
    Module-level shim for ``FingerprintHelpers.compute_call_fingerprint``.

    Args:
        capability (str): Provider capability.
        provider_id (str): Provider identifier.
        provider_version (str): Provider version string.
        params (dict): Call parameters.
        content_hash (str): Blake3 hash of the content being processed.

    Returns:
        str: 64-character hex blake3 digest.
    """
    return FingerprintHelpers.compute_call_fingerprint(
        capability, provider_id, provider_version, params, content_hash
    )
