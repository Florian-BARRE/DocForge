# ====== Code Summary ======
# BlobSecrets — secret redaction for the collection config blobs (pipeline + search), SHARED between the
# app (which masks secrets on every outbound collection read and restores them on a PATCH round-trip)
# and the worker (which masks secrets before writing a portable export bundle). The product STORES
# provider secrets per collection in clear (an accepted design choice), but must NEVER leak them off the
# server: not on a GET, and not inside an exported `.dcexport` bundle a READ-scoped key can download.
# This class is the ONE definition of "walk a node graph, mask/restore every provider secret field" (the
# name-keyed ``SECRET_FIELDS`` — ``api_key`` plus the gotenberg basic-auth ``password``, at the top level
# of a node config AND nested inside it, e.g. a metagen ``targets[*].api_key``), so the API surface and
# the export surface can never drift on what counts as a secret. On write, a masked/omitted secret is
# restored only for the same provider at the same effective endpoint; an endpoint change raises
# SecretReentryRequired instead of carrying the stored key to the new host, and so does a nested
# override (metagen target, structgen step) pointed at a foreign endpoint while omitting its own key.
# The function names callers import live in ``shared_libs.pipelines.blob_secrets`` (a thin facade).

# ====== Standard Library Imports ======
import copy
from collections.abc import Iterator
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.nested_secrets import NestedSecrets
from shared_libs.pipelines.nodes.embed.dense_sparse.legacy import (
    DENSE_SPARSE_KIND,
    EmbedLegacyMigration,
)
from shared_libs.pipelines.request_secret_guard import RequestSecretGuard
from shared_libs.pipelines.secret_identity import (
    SECRET_FIELDS,
    ProviderRef,
    SecretIdentity,
    SecretMatch,
)

# ====== Local Project Imports ======
from .secret_reentry_required import SecretReentryRequired

# The redaction marker that replaces every masked secret on the way out. It is a CONSTANT — no part of
# the real key survives (an earlier format leaked the last 4 chars as ``<MASK_PREFIX><last4>``) — so a
# client only learns that a key IS set. The value is deliberately un-key-like so no real provider key
# collides with it, and it doubles as the prefix the write path recognises.
MASK_PREFIX = "__redacted__"
MASK = MASK_PREFIX


class BlobSecrets:
    """Static mask / restore / probe of the provider secrets held by a pipeline or search blob."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobSecrets is a static-only class and cannot be instantiated.")

    # ------------------------------------------------------------------ #
    # Node walking
    # ------------------------------------------------------------------ #

    @classmethod
    def __nodes(cls, nodes: Any) -> Iterator[dict[str, Any]]:
        """Every node dict of a node list, parents first, recursing groups and foreach bodies.

        Nested group children live under ``nodes``; a foreach exposes its sub-graph under ``body``.
        """
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            yield node
            yield from cls.__nodes(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                yield from cls.__nodes(body.get("nodes"))

    @classmethod
    def __blob_nodes(cls, blob: dict | None) -> Iterator[dict[str, Any]]:
        """Every node of a blob (nothing for a non-dict blob)."""
        if isinstance(blob, dict):
            yield from cls.__nodes(blob.get("nodes"))

    @classmethod
    def __action_configs(cls, blob: dict | None) -> list[dict]:
        """Collect every action node's ``config`` dict in a blob (recursing groups and foreach bodies)."""
        return [
            node["config"]
            for node in cls.__blob_nodes(blob)
            if isinstance(node.get("config"), dict)
        ]

    @classmethod
    def __stored_providers(cls, blob: dict | None) -> dict[str, ProviderRef]:
        """Map node id → (family, kind, config) for every action node of the STORED blob.

        The secret source index of the write path: a node's secrets are restored from the stored node
        the identity rule picks (same id, family and kind at the same effective endpoint, or a
        same-kind chain sibling at that endpoint).
        """
        result: dict[str, ProviderRef] = {}
        for node in cls.__blob_nodes(blob):
            node_id = node.get("id")
            config = node.get("config")
            if isinstance(node_id, str) and isinstance(config, dict):
                result[node_id] = (node.get("family"), node.get("kind"), config)
        return result

    # ------------------------------------------------------------------ #
    # Masking
    # ------------------------------------------------------------------ #

    @classmethod
    def is_masked(cls, value: Any) -> bool:
        """True when a value is a redaction marker — the current constant OR the legacy last-4 form.

        Matching on the prefix keeps the round-trip contract for clients/UIs that still hold a mask
        read before the constant format (``__redacted__<last4>``): echoing it back still means "keep
        the key".
        """
        return isinstance(value, str) and value.startswith(MASK_PREFIX)

    @classmethod
    def __mask_secret(cls, value: Any) -> Any:
        """Mask one secret value: empty/blank stays empty, a real key becomes the constant marker."""
        if not isinstance(value, str) or value == "":
            return value
        return MASK

    @classmethod
    def has_secrets(cls, blob: dict | None) -> bool:
        """Return whether any action node in a blob carries a non-empty provider secret field.

        The cheap predicate behind the fleet-list masking optimization: when it returns False the
        masked outbound copy would be byte-identical to the input, so the caller can skip the
        defensive ``copy.deepcopy`` that ``redact`` always performs and serialise the stored blob
        as-is. Most collections run the stock in-stack pipeline (gotenberg/bge_server, no
        ``api_key``), so this is False for them and the per-row deepcopy is avoided entirely on the
        list path.

        Args:
            blob (dict | None): The stored pipeline or search blob (or ``None``/``{}``).

        Returns:
            bool: True as soon as one action node config holds a non-empty secret field value, at its
            top level or nested (e.g. a metagen ``targets[*].api_key``).
        """
        for config in cls.__action_configs(blob):
            for field in SECRET_FIELDS:
                value = config.get(field)
                if isinstance(value, str) and value != "":
                    return True
            if NestedSecrets.held(config):
                return True
        return False

    @classmethod
    def redact(cls, blob: dict | None) -> dict | None:
        """Return a deep copy of a pipeline/search blob with every provider secret masked.

        Every secret-named key is masked wherever it sits in a node config — top level, or nested in
        a dict/list such as a metagen ``targets[*].api_key``. The input (the stored blob) is never
        mutated — only the outbound copy is masked, so ingestion and search keep reading the real key
        from storage.

        Args:
            blob (dict | None): The stored pipeline or search blob (or ``None``/``{}``).

        Returns:
            dict | None: A masked copy safe to serialise to a client or write into an export bundle.
        """
        if not isinstance(blob, dict):
            return blob
        redacted = copy.deepcopy(blob)
        for config in cls.__action_configs(redacted):
            for field in SECRET_FIELDS:
                if field in config:
                    config[field] = cls.__mask_secret(config[field])
            NestedSecrets.mask(config, cls.__mask_secret)
        return redacted

    @classmethod
    def redact_snapshot(cls, config: dict | None) -> dict | None:
        """Return a masked copy of an archived config-version snapshot ``{"pipeline": …, "search": …}``.

        A ``config_versions[].config`` row is NOT a raw node blob — it wraps the pipeline and search
        blobs under their own keys (see ``CollectionsFacade`` add_config_version writers). Feeding it
        straight to ``redact`` would look for a top-level ``nodes`` list, find none, and pass the
        snapshot through with LIVE keys intact — leaking every historical provider secret into an
        export bundle. This redacts each wrapped sub-blob through the node walker and preserves any
        other snapshot keys verbatim.

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
                redacted[key] = cls.redact(redacted[key])
        return redacted

    # ------------------------------------------------------------------ #
    # Restoring (the write path)
    # ------------------------------------------------------------------ #

    @classmethod
    def as_slot_source(cls, node: dict, positional: ProviderRef | None) -> ProviderRef | None:
        """A legacy stored embed node seen as the dense_sparse node an inbound migrated blob carries.

        A stored blob written before the dense/sparse slots holds its key at the top level of a
        ``bge_server`` / ``openai_compatible`` node; the healed blob a client reads (and writes back)
        carries it inside the ``dense`` / ``sparse`` slots. Mapping the stored node through the same
        migration keeps that key restorable — same slot, same endpoint — instead of blanking the mask.
        """
        if (
            positional is None
            or node.get("family") != "embed"
            or node.get("kind") != DENSE_SPARSE_KIND
            or positional[0] != "embed"
            or not EmbedLegacyMigration.is_legacy(positional[1])
        ):
            return positional
        return (
            "embed",
            DENSE_SPARSE_KIND,
            EmbedLegacyMigration.config(str(positional[1]), positional[2]),
        )

    @classmethod
    def __chain_siblings(cls, stored: dict[str, ProviderRef], node_id: str) -> list[ProviderRef]:
        """The stored providers of the chain ``node_id`` is a positional step of (empty otherwise)."""
        prefix = SecretIdentity.chain_prefix(node_id)
        if prefix is None:
            return []
        return [
            ref for other, ref in stored.items() if SecretIdentity.chain_prefix(other) == prefix
        ]

    @classmethod
    def __real_secret(cls, source: dict | None, field: str) -> str | None:
        """The live (non-empty, non-masked) secret ``field`` of a stored config, else ``None``."""
        value = source.get(field) if source is not None else None
        if isinstance(value, str) and value != "" and not cls.is_masked(value):
            return value
        return None

    @classmethod
    def __heal_config(cls, config: dict, match: SecretMatch) -> list[str]:
        """Resolve one inbound node config's secrets in place against its identity match.

        Returns:
            list[str]: The secret fields that must be re-entered — masked/omitted while the same
            provider's stored key exists only at a DIFFERENT endpoint (never carried, never blanked).
        """
        reentry: list[str] = []
        for field in SECRET_FIELDS:
            masked = cls.is_masked(config.get(field))
            if not masked and field in config:
                continue
            real = cls.__real_secret(match.source, field)
            # 1. Same provider at the same endpoint — a mask or an omission keeps the stored key.
            if real is not None:
                config[field] = real
            # 2. The stored key exists but the endpoint moved — the caller must re-send it.
            elif cls.__real_secret(match.moved, field) is not None:
                reentry.append(field)
            # 3. No stored key for this provider — a mask is never persisted as a live key.
            elif masked:
                config[field] = ""
        return sorted(reentry)

    @classmethod
    def __heal_nested(cls, node: dict, positional: ProviderRef | None) -> list[str]:
        """Resolve one inbound node's NESTED secrets in place (its top level already healed).

        A masked/omitted nested secret is restored only from the stored same-provider node's item of
        the same identity (path, ``field``, effective endpoint); a nested override at a foreign
        endpoint that omits a secret its node holds is refused (it would rely on the node's key
        there).

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
        reentry = NestedSecrets.restore(config, endpoint, same_kind, stored_endpoint, cls.is_masked)
        return reentry + NestedSecrets.foreign_inheritors(config, endpoint)

    @classmethod
    def restore(cls, incoming: dict | None, stored: dict | None) -> dict | None:
        """Return a deep copy of an inbound blob with its secrets healed back to the stored keys.

        The write rule, per secret field of every action node:

        - a MASKED value means "keep the existing stored key", never "set the key to the literal mask";
        - an OMITTED field means the same (a caller editing a config need not re-send the key);
        - an explicit ``""`` clears the key, and any other value is a genuinely new key, kept verbatim.

        The stored key comes from the SAME provider at the SAME endpoint only
        (``SecretIdentity.pick``): the stored node of the same id, family and kind whose normalised
        EFFECTIVE endpoint (explicit ``base_url``, else the Config default — so an omitted and an
        explicit default compare equal) is unchanged — or, for a positional chain step, a same-kind
        sibling of that chain at that endpoint (a reorder). A kind mismatch never restores: a masked
        value with no same-provider source is blanked, an omitted one stays omitted. An ENDPOINT
        CHANGE never restores either, and is refused: a masked/omitted secret whose provider's stored
        key lives at another endpoint raises ``SecretReentryRequired`` (the key must be re-sent), so a
        stored key can neither be exfiltrated to a new host nor silently dropped.

        NESTED secrets (e.g. a metagen ``targets[*].api_key``) follow the same rule, paired by
        identity: the item's path, its ``field`` and its effective endpoint (own ``base_url``, else
        the node's). A nested key whose item endpoint changed is refused for re-entry, never carried.
        Finally a NESTED OVERRIDE that points at a foreign endpoint while OMITTING its key — a metagen
        target with its own ``base_url``, or a structgen step whose ``base_url`` matches none of the
        prep's keyed endpoints — is refused too: it could only work by inheriting the parent's key,
        which the runtime never sends to another host (an explicit ``""`` states a keyless override and
        is accepted).

        Args:
            incoming (dict | None): The blob the caller wrote back (may carry masks / omit secrets).
            stored (dict | None): The currently stored blob holding the real secrets.

        Returns:
            dict | None: A copy of ``incoming`` with secrets resolved, ready to persist.

        Raises:
            SecretReentryRequired: When a masked/omitted secret's provider endpoint changed, or a
                nested override relies on an inherited key at a foreign endpoint.
        """
        if not isinstance(incoming, dict):
            return incoming
        healed = copy.deepcopy(incoming)
        providers = cls.__stored_providers(stored)
        reentry: list[tuple[str, str]] = []
        for node in cls.__blob_nodes(healed):
            config = node.get("config")
            if not isinstance(config, dict):
                continue
            node_id = node.get("id")
            positional = cls.as_slot_source(
                node, providers.get(node_id) if isinstance(node_id, str) else None
            )
            siblings = cls.__chain_siblings(providers, node_id) if isinstance(node_id, str) else []
            match = SecretIdentity.pick(
                node.get("family"), node.get("kind"), config, positional, siblings
            )
            reentry.extend((str(node_id), field) for field in cls.__heal_config(config, match))
            reentry.extend((str(node_id), label) for label in cls.__heal_nested(node, positional))
        reentry.extend(RequestSecretGuard.violations(healed))
        if reentry:
            raise SecretReentryRequired(reentry)
        return healed
