# ====== Code Summary ======
# Secret redaction for the collection config blobs (pipeline + search) — SHARED between the app (which
# masks secrets on every outbound collection read and restores them on a PATCH round-trip) and the
# worker (which masks secrets before writing a portable export bundle). The product STORES provider
# secrets per collection in clear (an accepted design choice), but must NEVER leak them off the server:
# not on a GET, and not inside an exported `.dcexport` bundle a READ-scoped key can download. This
# module is the ONE definition of "walk a node graph, mask/restore every provider secret field" (the
# name-keyed ``SECRET_FIELDS`` — ``api_key`` plus the gotenberg basic-auth ``password``, at the top level
# of a node config AND nested inside it, e.g. a metagen ``targets[*].api_key``), so the API surface and
# the export surface can never drift on what counts as a secret. On write, a masked/omitted secret is
# restored only for the same provider at the same effective endpoint; an endpoint change raises
# SecretReentryRequired instead of carrying the stored key to the new host, and so does a nested
# override (metagen target, structgen step) pointed at a foreign endpoint while omitting its own key.

# ====== Standard Library Imports ======
import copy
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.nested_secrets import NestedSecrets
from shared_libs.pipelines.request_secret_guard import RequestSecretGuard
from shared_libs.pipelines.secret_identity import (
    SECRET_FIELDS,
    ProviderRef,
    SecretIdentity,
    SecretMatch,
)

# The redaction marker that replaces every masked secret on the way out. It is a CONSTANT — no part of
# the real key survives (an earlier format leaked the last 4 chars as ``<MASK_PREFIX><last4>``) — so a
# client only learns that a key IS set. The value is deliberately un-key-like so no real provider key
# collides with it, and it doubles as the prefix the write path recognises.
MASK_PREFIX = "__redacted__"
MASK = MASK_PREFIX


class SecretReentryRequired(ValueError):
    """
    Raised when a write would carry a stored or inherited provider secret onto ANOTHER endpoint.

    A masked / omitted secret means "keep the stored key" only for the same provider at the same
    effective endpoint. When the endpoint moved, carrying it would ship the stored key to a host the
    caller just named (exfiltration), and blanking it would silently persist a keyless provider — so
    the write is refused and the caller must re-send the secret (or ``""`` to clear it). The same
    refusal covers a NESTED endpoint override (a metagen target, a structgen step) pointed at a
    foreign endpoint while omitting its key: it could only work by inheriting the parent's key, which
    is never sent there. A ``ValueError`` so every write route maps it to a 422.
    """

    def __init__(self, fields: list[tuple[str, str]]) -> None:
        self.fields = fields
        named = ", ".join(f"node '{node_id}' {field}" for node_id, field in fields)
        super().__init__(
            f"{named} must be re-entered because its endpoint (base_url) differs from the one the "
            f"secret belongs to — a stored or inherited secret is only used for the same provider at "
            f'the same endpoint; send the secret explicitly (or "" to call it without one)'
        )


def _mask_secret(value: Any) -> Any:
    """Mask one secret value: empty/blank stays empty, a real key becomes the constant marker."""
    if not isinstance(value, str) or value == "":
        return value
    return MASK


def is_masked(value: Any) -> bool:
    """True when a value is a redaction marker — the current constant OR the legacy last-4 form.

    Matching on the prefix keeps the round-trip contract for clients/UIs that still hold a mask read
    before the constant format (``__redacted__<last4>``): echoing it back still means "keep the key".
    """
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


def _stored_providers(blob: dict | None) -> dict[str, ProviderRef]:
    """Map node id → (family, kind, config) for every action node of the STORED blob.

    The secret source index of the write path: a node's secrets are restored from the stored node the
    identity rule picks (same id, family and kind at the same effective endpoint, or a same-kind chain
    sibling at that endpoint).
    """
    result: dict[str, ProviderRef] = {}

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            config = node.get("config")
            if isinstance(node_id, str) and isinstance(config, dict):
                result[node_id] = (node.get("family"), node.get("kind"), config)
            walk(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes"))

    if isinstance(blob, dict):
        walk(blob.get("nodes"))
    return result


def _chain_siblings(stored: dict[str, ProviderRef], node_id: str) -> list[ProviderRef]:
    """The stored providers of the chain ``node_id`` is a positional step of (empty otherwise)."""
    prefix = SecretIdentity.chain_prefix(node_id)
    if prefix is None:
        return []
    return [ref for other, ref in stored.items() if SecretIdentity.chain_prefix(other) == prefix]


def _real_secret(source: dict | None, field: str) -> str | None:
    """The live (non-empty, non-masked) secret ``field`` of a stored config, else ``None``."""
    value = source.get(field) if source is not None else None
    if isinstance(value, str) and value != "" and not is_masked(value):
        return value
    return None


def _heal_config(config: dict, match: SecretMatch) -> list[str]:
    """Resolve one inbound node config's secrets in place against its identity match.

    Returns:
        list[str]: The secret fields that must be re-entered — masked/omitted while the same
        provider's stored key exists only at a DIFFERENT endpoint (never carried, never blanked).
    """
    reentry: list[str] = []
    for field in SECRET_FIELDS:
        masked = is_masked(config.get(field))
        if not masked and field in config:
            continue
        real = _real_secret(match.source, field)
        # 1. Same provider at the same endpoint — a mask or an omission keeps the stored key.
        if real is not None:
            config[field] = real
        # 2. The stored key exists but the endpoint moved — the caller must re-send it.
        elif _real_secret(match.moved, field) is not None:
            reentry.append(field)
        # 3. No stored key for this provider — a mask is never persisted as a live key.
        elif masked:
            config[field] = ""
    return sorted(reentry)


def _heal_nested(node: dict, positional: ProviderRef | None) -> list[str]:
    """Resolve one inbound node's NESTED secrets in place (its top level already healed).

    A masked/omitted nested secret is restored only from the stored same-provider node's item of the
    same identity (path, ``field``, effective endpoint); a nested override at a foreign endpoint that
    omits a secret its node holds is refused (it would rely on the node's key there).

    Returns:
        list[str]: The nested secret labels that must be (re-)entered.
    """
    family, kind, config = node.get("family"), node.get("kind"), node["config"]
    same_kind = (
        positional[2]
        if positional is not None and positional[0] == family and positional[1] == kind
        else None
    )
    endpoint = SecretIdentity.effective_endpoint(family, kind, config)
    stored_endpoint = (
        SecretIdentity.effective_endpoint(family, kind, same_kind)
        if same_kind is not None
        else None
    )
    reentry = NestedSecrets.restore(config, endpoint, same_kind, stored_endpoint, is_masked)
    return reentry + NestedSecrets.foreign_inheritors(config, endpoint)


def has_blob_secrets(blob: dict | None) -> bool:
    """Return whether any action node in a blob carries a non-empty provider secret field.

    The cheap predicate behind the fleet-list masking optimization: when it returns False the masked
    outbound copy would be byte-identical to the input, so the caller can skip the defensive
    ``copy.deepcopy`` that ``redact_blob_secrets`` always performs and serialise the stored blob as-is.
    Most collections run the stock in-stack pipeline (gotenberg/bge_server, no ``api_key``), so this is
    False for them and the per-row deepcopy is avoided entirely on the list path.

    Args:
        blob (dict | None): The stored pipeline or search blob (or ``None``/``{}``).

    Returns:
        bool: True as soon as one action node config holds a non-empty secret field value, at its
        top level or nested (e.g. a metagen ``targets[*].api_key``).
    """
    for config in _iter_action_configs(blob):
        for field in SECRET_FIELDS:
            value = config.get(field)
            if isinstance(value, str) and value != "":
                return True
        if NestedSecrets.held(config):
            return True
    return False


def redact_blob_secrets(blob: dict | None) -> dict | None:
    """Return a deep copy of a pipeline/search blob with every provider secret masked.

    Every secret-named key is masked wherever it sits in a node config — top level, or nested in a
    dict/list such as a metagen ``targets[*].api_key``. The input (the stored blob) is never mutated — only the outbound copy is masked, so ingestion and
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
        NestedSecrets.mask(config, _mask_secret)
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
    """Return a deep copy of an inbound blob with its secrets healed back to the stored keys.

    The write rule, per secret field of every action node:

    - a MASKED value means "keep the existing stored key", never "set the key to the literal mask";
    - an OMITTED field means the same (a caller editing a config need not re-send the key);
    - an explicit ``""`` clears the key, and any other value is a genuinely new key, kept verbatim.

    The stored key comes from the SAME provider at the SAME endpoint only (``SecretIdentity.pick``):
    the stored node of the same id, family and kind whose normalised EFFECTIVE endpoint (explicit
    ``base_url``, else the Config default — so an omitted and an explicit default compare equal) is
    unchanged — or, for a positional chain step, a same-kind sibling of that chain at that endpoint
    (a reorder). A kind mismatch never restores: a masked value with no same-provider source is
    blanked, an omitted one stays omitted. An ENDPOINT CHANGE never restores either, and is refused:
    a masked/omitted secret whose provider's stored key lives at another endpoint raises
    ``SecretReentryRequired`` (the key must be re-sent), so a stored key can neither be exfiltrated
    to a new host nor silently dropped.

    NESTED secrets (e.g. a metagen ``targets[*].api_key``) follow the same rule, paired by identity:
    the item's path, its ``field`` and its effective endpoint (own ``base_url``, else the node's). A
    nested key whose item endpoint changed is refused for re-entry, never carried. Finally a NESTED
    OVERRIDE that points at a foreign endpoint while OMITTING its key — a metagen target with its own
    ``base_url``, or a structgen step whose ``base_url`` matches none of the prep's keyed endpoints — is
    refused too: it could only work by inheriting the parent's key, which the runtime never sends to
    another host (an explicit ``""`` states a keyless override and is accepted).

    Args:
        incoming (dict | None): The blob the caller wrote back (may carry masks / omit secrets).
        stored (dict | None): The currently stored blob holding the real secrets.

    Returns:
        dict | None: A copy of ``incoming`` with secrets resolved, ready to persist.

    Raises:
        SecretReentryRequired: When a masked/omitted secret's provider endpoint changed, or a nested
            override relies on an inherited key at a foreign endpoint.
    """
    if not isinstance(incoming, dict):
        return incoming
    healed = copy.deepcopy(incoming)
    providers = _stored_providers(stored)
    reentry: list[tuple[str, str]] = []

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            config = node.get("config")
            if isinstance(config, dict):
                positional = providers.get(node_id) if isinstance(node_id, str) else None
                siblings = _chain_siblings(providers, node_id) if isinstance(node_id, str) else []
                family, kind = node.get("family"), node.get("kind")
                match = SecretIdentity.pick(family, kind, config, positional, siblings)
                reentry.extend((str(node_id), field) for field in _heal_config(config, match))
                reentry.extend((str(node_id), label) for label in _heal_nested(node, positional))
            walk(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                walk(body.get("nodes"))

    walk(healed.get("nodes"))
    reentry.extend(RequestSecretGuard.violations(healed))
    if reentry:
        raise SecretReentryRequired(reentry)
    return healed


__all__ = [
    "SECRET_FIELDS",
    "MASK_PREFIX",
    "MASK",
    "SecretReentryRequired",
    "is_masked",
    "has_blob_secrets",
    "redact_blob_secrets",
    "restore_blob_secrets",
]
