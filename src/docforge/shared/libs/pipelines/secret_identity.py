# ====== Code Summary ======
# SecretIdentity — decides WHICH previously-stored node config a provider secret may be carried from,
# shared by the write-side restore (blob_secrets.restore_blob_secrets) and the stage compiler's chain
# rebuilds (ChainSecretCarry). A secret belongs to a provider AT AN ENDPOINT, never to a position:
# chain step ids are positional (``f"{prefix}_{index}"``), so a reorder would otherwise hand one
# provider's key to another, and an endpoint edit would otherwise ship the stored key to whatever host
# the caller names. The rule: a secret is carried ONLY from a stored config of the SAME family and kind
# whose normalised EFFECTIVE endpoint equals the incoming one — the positional node, else a same-kind
# sibling of the same chain at that endpoint (a reorder). A same-kind positional node whose endpoint
# moved is reported as ``moved``: its secret must be re-entered, never silently carried.
# ``scoped_secret`` is the RUNTIME half for nested endpoint overrides (metagen targets, structgen steps):
# the parent's key is inherited only at the parent's own endpoint, never sent to a foreign base_url.

# ====== Standard Library Imports ======
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# The provider-node config keys that hold a secret, matched by NAME across every node config. Most
# provider nodes (openai_compat llm/vlm/embed, mistral ocr/llm, bge_server embed, structgen,
# cross_encoder rerank) declare their secret as a TOP-LEVEL "api_key"; the gotenberg converter adds a
# basic-auth "password" for a remote instance (its "username" is NOT a secret and stays clear). Any
# future field named "api_key"/"password" is auto-covered — audited across the node Config models.
SECRET_FIELDS: frozenset[str] = frozenset({"api_key", "password"})

# The config key naming a provider's endpoint — the destination a secret is sent to.
ENDPOINT_FIELD = "base_url"

# Implicit ports, so ``https://h`` and ``https://h:443`` are the same endpoint.
_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}

# A (family, kind, config) triple — one provider node as seen by the identity rule.
type ProviderRef = tuple[str | None, str | None, dict[str, Any]]


@dataclass(frozen=True)
class SecretMatch:
    """
    The outcome of the identity rule for one incoming provider node.

    Attributes:
        source (dict | None): The stored config whose secrets may be carried (same provider, same
            effective endpoint), or ``None``.
        moved (dict | None): The stored same-kind config at this position whose endpoint CHANGED —
            its secrets must be re-entered, never carried. ``None`` when ``source`` is set.
    """

    source: dict[str, Any] | None = None
    moved: dict[str, Any] | None = None


class SecretIdentity:
    """Static rule picking the stored provider config a node's secrets may come from."""

    # A chain step id is ``f"{prefix}_{index}"`` (ChainFragmentBuilder) — the prefix names the chain.
    _CHAIN_STEP_ID = re.compile(r"^(?P<prefix>.+)_\d+$")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SecretIdentity is a static-only class and cannot be instantiated.")

    @staticmethod
    def normalize(url: Any) -> str | None:
        """
        Normalise an endpoint URL: lower-cased scheme + host, explicit port, path without its
        trailing slash (path and query keep their case). ``None`` for a blank / non-string value.
        An unparseable port yields the raw lower-cased string — never the scheme's default port, so
        ``https://h:bogus`` can never compare equal to ``https://h``.
        """
        if not isinstance(url, str) or not url.strip():
            return None
        raw = url.strip()
        parts = urlsplit(raw)
        try:
            port = parts.port
        except ValueError:
            return raw.lower()
        if not parts.scheme or not parts.hostname:
            return raw.rstrip("/").lower()
        scheme = parts.scheme.lower()
        port = port or _DEFAULT_PORTS.get(scheme)
        query = f"?{parts.query}" if parts.query else ""
        return f"{scheme}://{parts.hostname.lower()}:{port}{parts.path.rstrip('/')}{query}"

    @classmethod
    def same_endpoint(cls, left: Any, right: Any) -> bool:
        """Whether two endpoint URLs normalise to the same NON-blank endpoint."""
        normalized = cls.normalize(left)
        return normalized is not None and normalized == cls.normalize(right)

    @classmethod
    def scoped_secret(
        cls, override_url: str, override_secret: str, parent_url: str, parent_secret: str
    ) -> str:
        """
        The secret an endpoint OVERRIDE may send — the runtime half of the endpoint rule.

        A secret is bound to the endpoint DECLARED next to it. A nested endpoint override (a metagen
        per-field target, a structgen fallback step) with its OWN ``base_url`` sends its own secret
        there — possibly ``""`` (no key at all) — and inherits the parent's secret only when that
        ``base_url`` normalises to the parent's. An override with a BLANK ``base_url`` calls the
        parent's endpoint, so it always sends the parent's secret and its own is ignored: an
        endpoint-less key would otherwise follow wherever a caller moves the parent (a write that
        redirects the parent and blanks only the parent's key would ship the override's key to the
        new host). Enforced at run time, it also protects blobs stored before the write rule.

        Args:
            override_url (str): The override's ``base_url`` (blank = the parent's endpoint).
            override_secret (str): The override's own secret (used only with its own ``base_url``).
            parent_url (str): The parent's ``base_url`` — where ``parent_secret`` belongs.
            parent_secret (str): The parent's secret.

        Returns:
            str: The parent's secret for a blank override endpoint; otherwise the override's own
            secret, else the parent's when both endpoints are the same, else ``""``.
        """
        # 1. No endpoint of its own → it calls the parent's endpoint with the parent's secret.
        if cls.normalize(override_url) is None:
            return parent_secret
        # 2. Its own endpoint → its own secret, or the parent's only at the very same endpoint.
        if override_secret:
            return override_secret
        return parent_secret if cls.same_endpoint(override_url, parent_url) else ""

    @classmethod
    def endpoint(cls, config: dict[str, Any] | None) -> str | None:
        """The node's EXPLICIT normalised endpoint (its ``base_url``), or ``None`` when undeclared."""
        return cls.normalize((config or {}).get(ENDPOINT_FIELD))

    @staticmethod
    def default_endpoint(family: str | None, kind: str | None) -> str | None:
        """The ``base_url`` schema default of the registered ``(family, kind)`` Config, if any."""
        try:
            config_model = NodeRegistry.get(family, kind).Config
        except (KeyError, AttributeError):
            return None
        field = config_model.model_fields.get(ENDPOINT_FIELD)
        if field is None or field.is_required():
            return None
        default = field.get_default(call_default_factory=True)
        return default if isinstance(default, str) else None

    @classmethod
    def effective_endpoint(
        cls, family: str | None, kind: str | None, config: dict[str, Any] | None
    ) -> str | None:
        """The endpoint the node will ACTUALLY call: its explicit ``base_url``, else the default."""
        explicit = cls.endpoint(config)
        return (
            explicit if explicit is not None else cls.normalize(cls.default_endpoint(family, kind))
        )

    @classmethod
    def chain_prefix(cls, node_id: str | None) -> str | None:
        """The chain a positional step id belongs to (``None`` for a non-step id)."""
        if not isinstance(node_id, str):
            return None
        match = cls._CHAIN_STEP_ID.match(node_id)
        return match.group("prefix") if match else None

    @classmethod
    def pick(
        cls,
        family: str | None,
        kind: str | None,
        config: dict[str, Any],
        positional: ProviderRef | None,
        siblings: list[ProviderRef],
    ) -> SecretMatch:
        """
        The stored config whose secrets may be carried onto ``(family, kind, config)``.

        Args:
            family (str | None): The incoming node's registry family.
            kind (str | None): The incoming node's registry kind.
            config (dict): The incoming node's config (its effective endpoint is the key).
            positional (ProviderRef | None): The stored node at the same id / chain position.
            siblings (list[ProviderRef]): The stored providers of the same chain (any position).

        Returns:
            SecretMatch: ``source`` — a same-family, same-kind stored config at the SAME effective
            endpoint (positional first, then a chain sibling); otherwise ``moved`` — the same-kind
            positional config whose endpoint changed (secrets must be re-entered), or nothing.
        """
        # 1. The positional source counts only when it is the same provider type (a provider swap
        #    never inherits the previous provider's key).
        same_kind = (
            positional[2]
            if positional is not None and positional[0] == family and positional[1] == kind
            else None
        )
        target = cls.effective_endpoint(family, kind, config)

        # 2. Same provider at the same effective endpoint — the common unchanged case.
        if same_kind is not None and cls.effective_endpoint(family, kind, same_kind) == target:
            return SecretMatch(source=same_kind)

        # 3. A same-kind sibling at the SAME explicit endpoint — the provider moved within its chain.
        #    A node without an explicit base_url is never matched across positions: two default-URL
        #    steps of one kind are indistinguishable, so a reorder must not swap their keys.
        explicit = cls.endpoint(config) is not None
        for sibling_family, sibling_kind, sibling_config in siblings if explicit else []:
            if (
                sibling_family == family
                and sibling_kind == kind
                and cls.effective_endpoint(family, kind, sibling_config) == target
            ):
                return SecretMatch(source=sibling_config)

        # 4. Same kind, endpoint changed (no stored provider owns the new endpoint) — never carry.
        return SecretMatch(moved=same_kind)


__all__ = ["ENDPOINT_FIELD", "SECRET_FIELDS", "ProviderRef", "SecretIdentity", "SecretMatch"]
