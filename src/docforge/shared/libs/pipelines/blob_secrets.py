# ====== Code Summary ======
# Secret redaction for the collection config blobs (pipeline + search) — SHARED between the app (which
# masks secrets on every outbound collection read and restores them on a PATCH round-trip) and the
# worker (which masks secrets before writing a portable export bundle). The product STORES provider
# secrets per collection in clear (an accepted design choice), but must NEVER leak them off the server:
# not on a GET, and not inside an exported `.dcexport` bundle a READ-scoped key can download. This
# module is the ONE definition of "walk a node graph, mask/restore every provider ``api_key``", so the
# API surface and the export surface can never drift on what counts as a secret.

# ====== Standard Library Imports ======
import copy
from typing import Any

# The provider-node config keys that hold a secret. Every provider node (openai_compat llm/vlm/embed,
# mistral ocr/llm, bge_server embed, structgen, cross_encoder rerank) declares its secret as a
# TOP-LEVEL config key named exactly "api_key" — audited across the node Config models.
SECRET_FIELDS: frozenset[str] = frozenset({"api_key"})

# Marker prefixing every masked secret. A masked value is NON-reversible (only the last 4 chars of the
# real key survive, purely so an operator can tell a key is set and which one) and is recognisable on
# write via this prefix, which lets the round-trip keep the stored key instead of persisting the mask.
# The prefix is deliberately un-key-like so no real provider key collides with it.
MASK_PREFIX = "__redacted__"


def _mask_secret(value: Any) -> Any:
    """Mask one secret value: empty/blank stays empty, a real key becomes a non-reversible marker."""
    if not isinstance(value, str) or value == "":
        return value
    return f"{MASK_PREFIX}{value[-4:]}"


def is_masked(value: Any) -> bool:
    """True when a value is a redaction marker this module produced (recognised on write)."""
    return isinstance(value, str) and value.startswith(MASK_PREFIX)


def _iter_action_configs(blob: dict | None) -> "list[dict]":
    """Collect every action node's ``config`` dict in a blob (recursing groups and foreach bodies)."""
    configs: list[dict] = []

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            config = node.get("config")
            if isinstance(config, dict):
                configs.append(config)
            # Nested group children live under "nodes"; a foreach exposes its sub-graph under "body".
            walk(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes"))

    if isinstance(blob, dict):
        walk(blob.get("nodes"))
    return configs


def _secret_by_node_id(blob: dict | None) -> dict[str, dict[str, str]]:
    """Map node id → {secret_field: real_value} for every action node carrying a secret in ``blob``.

    Used on write to restore the real key of a node whose masked value came back untouched.
    """
    result: dict[str, dict[str, str]] = {}

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            config = node.get("config")
            if isinstance(node_id, str) and isinstance(config, dict):
                secrets = {
                    field: config[field]
                    for field in SECRET_FIELDS
                    if isinstance(config.get(field), str) and config[field] != ""
                }
                if secrets:
                    result[node_id] = secrets
            walk(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes"))

    if isinstance(blob, dict):
        walk(blob.get("nodes"))
    return result


def redact_blob_secrets(blob: dict | None) -> dict | None:
    """Return a deep copy of a pipeline/search blob with every provider secret masked.

    The input (the stored blob) is never mutated — only the outbound copy is masked, so ingestion and
    search keep reading the real key from storage.

    Args:
        blob (dict | None): The stored pipeline or search blob (or ``None``/``{}``).

    Returns:
        dict | None: A masked copy safe to serialise to a client or write into an export bundle.
    """
    if not isinstance(blob, dict):
        return blob
    redacted = copy.deepcopy(blob)
    for config in _iter_action_configs(redacted):
        for field in SECRET_FIELDS:
            if field in config:
                config[field] = _mask_secret(config[field])
    return redacted


def redact_config_snapshot(config: dict | None) -> dict | None:
    """Return a masked copy of an archived config-version snapshot ``{"pipeline": …, "search": …}``.

    A ``config_versions[].config`` row is NOT a raw node blob — it wraps the pipeline and search blobs
    under their own keys (see ``CollectionsFacade`` add_config_version writers). Feeding it straight to
    ``redact_blob_secrets`` would look for a top-level ``nodes`` list, find none, and pass the snapshot
    through with LIVE keys intact — leaking every historical provider secret into an export bundle. This
    redacts each wrapped sub-blob through the node walker and preserves any other snapshot keys verbatim.

    Args:
        config (dict | None): The stored config-version snapshot (or ``None``/``{}``).

    Returns:
        dict | None: A masked copy safe to write into an export bundle.
    """
    if not isinstance(config, dict):
        return config
    redacted = copy.deepcopy(config)
    for key in ("pipeline", "search"):
        if isinstance(redacted.get(key), dict):
            redacted[key] = redact_blob_secrets(redacted[key])
    return redacted


def restore_blob_secrets(incoming: dict | None, stored: dict | None) -> dict | None:
    """Return a deep copy of an inbound blob with masked secrets healed back to the stored key.

    The write rule: a masked secret value means "keep the existing stored key", NOT "set the key to the
    literal mask". So for every action node whose secret field is a redaction marker, the real value is
    restored from the stored blob's node of the same id. A masked value with no stored counterpart is
    blanked ("") — a fake mask must never be persisted as a live key. A NON-masked value (a genuinely
    new key, or an intentional clear to "") is kept verbatim.

    Args:
        incoming (dict | None): The blob the caller PATCHed back (may carry masks).
        stored (dict | None): The currently stored blob holding the real secrets.

    Returns:
        dict | None: A copy of ``incoming`` with masks resolved, ready to persist.
    """
    if not isinstance(incoming, dict):
        return incoming
    healed = copy.deepcopy(incoming)
    stored_secrets = _secret_by_node_id(stored)

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            config = node.get("config")
            if isinstance(config, dict):
                for field in SECRET_FIELDS:
                    if is_masked(config.get(field)):
                        real = stored_secrets.get(node_id, {}).get(field) if node_id else None
                        config[field] = real if real is not None else ""
            walk(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes"))

    walk(healed.get("nodes"))
    return healed


__all__ = [
    "SECRET_FIELDS",
    "MASK_PREFIX",
    "is_masked",
    "redact_blob_secrets",
    "restore_blob_secrets",
]
