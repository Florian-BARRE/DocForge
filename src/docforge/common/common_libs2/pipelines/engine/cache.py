# ====== Code Summary ======
# The caching seam — Protocols only. Fingerprinting and the node-cache backend are environment
# concerns (blake3 + Postgres/S3), so the engine depends only on these ports, never on a concrete
# implementation. The default NullFingerprint yields a stable empty key so the standalone engine
# runs with no cache. The real node-cache load/store is performed through EngineHooks.cache_load /
# cache_store (which can compute their own keys); these ports exist so a future in-engine cache
# middleware has a typed contract to target.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Internal Project Imports ======
from ..base import AbstractNode, NodeInput


@runtime_checkable
class FingerprintPort(Protocol):
    """
    Computes a node's cache key from its identity + resolved input + upstream fingerprints.

    The concrete implementation (blake3 Merkle node fingerprint) lives in a deployment; the engine
    only needs this call.
    """

    def fingerprint(
        self,
        node: AbstractNode,
        node_input: NodeInput,
        upstream_fingerprints: list[str],
    ) -> str:
        """Return the stable fingerprint for this node instance in this run."""
        ...


class NullFingerprint:
    """No-op fingerprint — yields an empty key so the standalone engine needs no fingerprinting."""

    def fingerprint(
        self,
        node: AbstractNode,
        node_input: NodeInput,
        upstream_fingerprints: list[str],
    ) -> str:
        """Return an empty fingerprint (caching is then a no-op via the hooks)."""
        return ""


__all__ = ["FingerprintPort", "NullFingerprint"]
