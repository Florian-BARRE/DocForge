# ====== Code Summary ======
# EmbedVectorSpace — the embed half of the index signature: a CANONICAL fingerprint of every embed
# node's vector-space-affecting config, and the LEGACY-equivalent fingerprints of that same space.
# Canonical: a legacy single-provider embed node (bge_server / openai_compatible) is first mapped onto
# the (embed, dense_sparse) slots, then each slot is fingerprinted from its VALIDATED config (defaults
# filled, so an omitted and an explicit default compare equal) minus the call-policy keys (key,
# timeouts, retries, concurrency — they never change a vector). Legacy-equivalent: the fingerprint
# format stored before the slots (``(id, kind, base_url/model/embed_sparse/embed_semantic_fields)``,
# raw values) for every legacy spelling the slot config may have been migrated from — so a collection
# indexed before the slots, whose blob healed to dense_sparse, does NOT flip to needs_reindex.

# ====== Standard Library Imports ======
import copy
import itertools
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.dense_sparse import (
    DENSE_SPARSE_KIND,
    IN_STACK_BGE_URL,
    EmbedLegacyMigration,
)
from shared_libs.pipelines.nodes.embed.providers import EmbedAxis, EmbedProviderRegistry

# Slot keys that never change the vectors (who/how the call is made, not what it computes).
_POLICY_KEYS = frozenset(
    {
        "api_key",
        "timeout_seconds",
        "preflight_timeout_seconds",
        "max_retries",
        "retry_backoff_seconds",
        "max_concurrency",
    }
)

# The pre-slots fingerprint keys (CollectionIndexSignature before the dense/sparse slots).
_LEGACY_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


class EmbedVectorSpace:
    """Static canonical + legacy-equivalent fingerprints of a blob's embed vector space."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedVectorSpace is a static-only class and cannot be instantiated.")

    @staticmethod
    def __embed_nodes(blob: dict) -> list[dict]:
        """Every embed-family node of a blob, recursing ForEach bodies and nested groups."""
        found: list[dict] = []

        def walk(nodes: list) -> None:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("family") == "embed":
                    found.append(node)
                walk(node.get("nodes") or [])
                body = node.get("body")
                if isinstance(body, dict):
                    walk(body.get("nodes") or [])

        walk((blob or {}).get("nodes") or [])
        return found

    @staticmethod
    def __slots_config(node: dict) -> dict[str, Any] | None:
        """The node's dense_sparse config (a legacy node migrated); None for any other kind."""
        kind, config = EmbedLegacyMigration.step(
            str(node.get("kind")), dict(node.get("config") or {})
        )
        return config if kind == DENSE_SPARSE_KIND else None

    @staticmethod
    def __slot_value(config: dict[str, Any], slot: str) -> dict[str, Any] | None:
        """A slot's raw value — an omitted slot is the stock in-stack bge_server."""
        value = config.get(slot, {"kind": "bge_server", "base_url": IN_STACK_BGE_URL})
        return value if isinstance(value, dict) else None

    @classmethod
    def __slot_fingerprint(cls, axis: EmbedAxis, value: dict[str, Any] | None) -> list | None:
        """A slot's vector-affecting config, sorted (validated when it validates, raw otherwise)."""
        if value is None:
            return None
        try:
            dumped = EmbedProviderRegistry.validate(axis, value).model_dump(mode="json")
        except (ValueError, ValidationError):
            dumped = dict(value)
        if isinstance(dumped.get("base_url"), str):
            dumped["base_url"] = dumped["base_url"].strip().rstrip("/")
        return sorted((k, v) for k, v in dumped.items() if k not in _POLICY_KEYS)

    @classmethod
    def canonical(cls, blob: dict) -> list:
        """
        The canonical, sorted per-embed-node fingerprint of a pipeline blob.

        Args:
            blob (dict): The stored ingestion pipeline blob (legacy or slot-shaped).

        Returns:
            list: One tuple per embed node — identical for a legacy node and its migrated form.
        """
        fingerprint: list = []
        for node in cls.__embed_nodes(blob):
            config = cls.__slots_config(node)
            if config is None:
                # An unknown/third-party kind keeps the pre-slots format (values, not just keys).
                raw = node.get("config") or {}
                fingerprint.append(
                    (node.get("id"), node.get("kind"), tuple((k, raw.get(k)) for k in _LEGACY_KEYS))
                )
                continue
            fingerprint.append(
                (
                    node.get("id"),
                    DENSE_SPARSE_KIND,
                    cls.__slot_fingerprint(EmbedAxis.DENSE, cls.__slot_value(config, "dense")),
                    cls.__slot_fingerprint(EmbedAxis.SPARSE, cls.__slot_value(config, "sparse")),
                    bool(config.get("embed_semantic_fields", False)),
                    bool(config.get("embed_lexical_fields", False)),
                )
            )
        return sorted(fingerprint, key=repr)

    @staticmethod
    def __flag_spellings(value: Any) -> list[Any]:
        """The raw legacy spellings of a boolean knob (absent ≡ the default)."""
        if value is None or value is False:
            return [None, False]
        return [value]

    @classmethod
    def __legacy_node_variants(cls, node: dict) -> list[tuple] | None:
        """The pre-slots fingerprints a dense_sparse node may have been migrated from (None: none)."""
        config = cls.__slots_config(node)
        if config is None:
            return None
        dense, sparse = cls.__slot_value(config, "dense"), cls.__slot_value(config, "sparse")
        if dense is None:
            return None
        kind = dense.get("kind")
        if kind == "bge_server":
            same = (
                sparse is not None
                and sparse.get("kind") == kind
                and (
                    str(sparse.get("base_url", "")).rstrip("/")
                    == str(dense.get("base_url", "")).rstrip("/")
                )
            )
            if sparse is not None and not same:
                return None
            embed_sparse = [None, True] if sparse is not None else [False]
        elif kind == "openai_compatible" and sparse is None:
            embed_sparse = [None, True, False]
        else:
            return None
        models = [dense.get("model")]
        provider_default = EmbedProviderRegistry.get(kind).Config.model_fields["model"].default
        if dense.get("model") in (None, provider_default):
            models = list(dict.fromkeys([dense.get("model"), None, provider_default]))
        semantic = cls.__flag_spellings(config.get("embed_semantic_fields"))
        return [
            (node.get("id"), kind, tuple(zip(_LEGACY_KEYS, (dense.get("base_url"), m, s, f))))
            for m, s, f in itertools.product(models, embed_sparse, semantic)
        ]

    @classmethod
    def sparse_rewrites(cls, blob: dict) -> list[dict]:
        """
        Copies of ``blob`` whose embed nodes' sparse slot is each plausible PRE-switch value.

        The candidates an older baseline (hashed whole, not per axis) may have been indexed under
        with the same dense slot: sparse off, the dense slot's own bge_server endpoint (the combined
        stock form), and the in-stack bge_server.

        Args:
            blob (dict): The stored ingestion pipeline blob.

        Returns:
            list[dict]: One rewritten blob per candidate sparse value (legacy nodes migrated).
        """
        variants: list[dict[str, Any] | None] = [
            None,
            {"kind": "bge_server", "base_url": IN_STACK_BGE_URL},
        ]
        rewrites: list[dict] = []
        for index in range(len(variants) + 1):
            copied = copy.deepcopy(blob or {})
            for node in cls.__embed_nodes(copied):
                config = cls.__slots_config(node)
                if config is None:
                    continue
                dense = cls.__slot_value(config, "dense")
                if index < len(variants):
                    config["sparse"] = variants[index]
                elif dense is not None and dense.get("kind") == "bge_server":
                    config["sparse"] = {"kind": "bge_server", "base_url": dense.get("base_url")}
                node["kind"], node["config"] = DENSE_SPARSE_KIND, config
            rewrites.append(copied)
        return rewrites

    @classmethod
    def legacy_equivalents(cls, blob: dict) -> list[list]:
        """
        Every pre-slots fingerprint (sorted node list) equivalent to the blob's embed space.

        Args:
            blob (dict): The stored ingestion pipeline blob.

        Returns:
            list[list]: The candidate legacy fingerprints; empty when the space has no legacy form
                (e.g. a bm25_local sparse slot, which did not exist before the slots).
        """
        per_node = [cls.__legacy_node_variants(node) for node in cls.__embed_nodes(blob)]
        if not per_node or any(variants is None for variants in per_node):
            return []
        return [sorted(combo) for combo in itertools.product(*per_node)]  # type: ignore[arg-type]


__all__ = ["EmbedVectorSpace"]
