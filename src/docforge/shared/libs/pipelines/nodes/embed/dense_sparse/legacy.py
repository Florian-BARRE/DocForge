# ====== Code Summary ======
# EmbedLegacyMigration — the ONE pure mapping from a pre-slots embed step (``bge_server`` /
# ``openai_compatible`` single-provider node) to the ``(embed, dense_sparse)`` slot config. Shared by
# the stage reader (blob heal), the chain handler (a legacy kind re-stated by a caller), the secret
# restore (a legacy stored node is the secret source of its migrated slots) and the index signature
# (a legacy blob and its migrated form fingerprint the same vector space). Only the keys present are
# copied, so an omitted knob keeps falling back to the same schema default.

# ====== Standard Library Imports ======
from typing import Any

# The dense_sparse kind every legacy embed step migrates to.
DENSE_SPARSE_KIND = "dense_sparse"

# The pre-slots single-provider embed kinds.
LEGACY_KINDS = frozenset({"bge_server", "openai_compatible"})

# Legacy top-level keys that move INTO a provider slot (endpoint, model, call policy).
_SLOT_KEYS = (
    "base_url",
    "api_key",
    "model",
    "timeout_seconds",
    "preflight_timeout_seconds",
    "max_retries",
    "retry_backoff_seconds",
    "max_concurrency",
)

# Legacy top-level keys that stay on the dense_sparse node itself.
_NODE_KEYS = ("batch_size", "embed_semantic_fields", "embed_lexical_fields")


class EmbedLegacyMigration:
    """Static mapping of a legacy single-provider embed step onto the dense/sparse slot config."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedLegacyMigration is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_legacy(kind: str | None) -> bool:
        """Whether an embed kind is a pre-slots single-provider node."""
        return kind in LEGACY_KINDS

    @staticmethod
    def config(kind: str, legacy: dict[str, Any]) -> dict[str, Any]:
        """
        The dense_sparse config equivalent to a legacy embed step's config.

        bge_server → the same endpoint in both slots (one combined call), or dense only when its
        ``embed_sparse`` was false; openai_compatible → dense only (the protocol has no sparse).

        Args:
            kind (str): The legacy kind (``bge_server`` / ``openai_compatible``).
            legacy (dict): The legacy node config.

        Returns:
            dict: The ``(embed, dense_sparse)`` config.
        """
        # 1. The provider slot carries the endpoint, model and call policy keys present.
        slot = {"kind": kind, **{key: legacy[key] for key in _SLOT_KEYS if key in legacy}}
        # 2. Sparse: bge keeps its sparse axis unless explicitly off; openai has none.
        sparse_on = kind == "bge_server" and legacy.get("embed_sparse", True) is not False
        migrated: dict[str, Any] = {"dense": slot, "sparse": dict(slot) if sparse_on else None}
        # 3. The node-level knobs stay top-level.
        migrated.update({key: legacy[key] for key in _NODE_KEYS if key in legacy})
        return migrated

    @classmethod
    def step(cls, kind: str, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """``(kind, config)`` migrated when legacy, unchanged otherwise."""
        if not cls.is_legacy(kind):
            return kind, config
        return DENSE_SPARSE_KIND, cls.config(kind, config)


__all__ = ["EmbedLegacyMigration", "DENSE_SPARSE_KIND", "LEGACY_KINDS"]
