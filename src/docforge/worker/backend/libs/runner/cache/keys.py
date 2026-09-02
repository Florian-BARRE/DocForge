# ====== Code Summary ======
# CacheKeyBuilder — the Merkle key composition for one cacheable stage. The key is a sha256 over five
# components joined with a reserved separator: (1) input_fp = sha256 of the ACTUAL upstream artefact
# the stage consumed (its real content bytes, so any upstream change ripples the key), (2) config_fp
# = sha256 of the stage's WHOLE normalised config subtree (extra="forbid" guarantees completeness —
# no hand-picked subset), (3) node identity family/kind (a provider swap changes the key), (4) the
# node CACHE_VERSION + the global ENGINE_CACHE_EPOCH (code/engine drift defence), and (5) the
# collection_id — the per-collection isolation the user chose (no cross-collection sharing). A wrong
# hit is worse than no cache, so every component is content-derived; two inputs collide only if they
# are genuinely identical parses of identical bytes under identical config in the same collection.

# ====== Standard Library Imports ======
import hashlib
import json
import uuid

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import ENGINE_CACHE_EPOCH

# ====== Local Project Imports ======
from .codec import ArtifactCodec

# A byte that cannot appear inside any component (all are hex digests or plain ascii tokens), so the
# join is unambiguous — no component boundary can be forged by a value straddling the separator.
_SEP = "\x1f"


class CacheKeyBuilder:
    """Static Merkle cache-key composition for a cacheable stage node."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CacheKeyBuilder is a static-only class and cannot be instantiated.")

    @staticmethod
    def config_fingerprint(config: dict) -> str:
        """sha256 of the stage's normalised config subtree (whole subtree, stable key order)."""
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def input_fingerprint(resolved_input: BaseModel) -> str:
        """sha256 of the real upstream artefact the stage consumed (its serialised content bytes)."""
        return ArtifactCodec.sha256(ArtifactCodec.pack(resolved_input))

    @classmethod
    def build(
        cls,
        *,
        family: str,
        kind: str,
        cache_version: str,
        config: dict,
        resolved_input: BaseModel,
        collection_id: uuid.UUID,
    ) -> str:
        """
        Compose the full stage cache key for this node + input + collection.

        Args:
            family (str): The node's registry family (e.g. ``parser``).
            kind (str): The node's registry kind (e.g. ``docling``).
            cache_version (str): The node's CACHE_VERSION (folded with the engine epoch).
            config (dict): The node's normalised config subtree (from the healed blob).
            resolved_input (BaseModel): The exact Consumes instance the engine resolved.
            collection_id (uuid.UUID): The owning collection — per-collection isolation.

        Returns:
            str: The sha256 hex cache key.
        """
        components = (
            cls.input_fingerprint(resolved_input),
            cls.config_fingerprint(config),
            f"{family}/{kind}",
            f"{cache_version}.{ENGINE_CACHE_EPOCH}",
            str(collection_id),
        )
        return hashlib.sha256(_SEP.join(components).encode()).hexdigest()


__all__ = ["CacheKeyBuilder"]
