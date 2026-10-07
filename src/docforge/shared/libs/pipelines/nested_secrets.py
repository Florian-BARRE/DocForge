# ====== Code Summary ======
# NestedSecrets — the endpoint rule for secrets held INSIDE a node config rather than at its top level:
# a metagen per-field target (``targets[*].api_key`` next to its own ``targets[*].base_url``) is a
# nested endpoint override. Three duties, all keyed on the secret NAME (SECRET_FIELDS) wherever it
# sits in the config (dicts and lists, recursively): mask it on the way out; restore a masked/omitted
# nested secret on write only from the stored item with the same identity — its path, its ``field``
# and its EFFECTIVE endpoint (own ``base_url``, else the parent's); and refuse a nested override that
# points at a foreign endpoint while omitting its secret (it would rely on the parent's key, which the
# runtime never sends there — see SecretIdentity.scoped_secret).

# ====== Standard Library Imports ======
import copy
from collections.abc import Callable, Iterator
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.secret_identity import SECRET_FIELDS, SecretIdentity

# A nested item's location inside its node config: the dict keys walked to reach it (list indices
# dropped, so a reordered list keeps its identity).
type NestedPath = tuple[str, ...]

# The identity a nested item's secret belongs to: (path, its ``field`` name, its effective endpoint).
type NestedIdentity = tuple[NestedPath, Any, str | None]


class NestedSecrets:
    """Static mask / restore / inheritance guard for the secrets nested inside one node config."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("NestedSecrets is a static-only class and cannot be instantiated.")

    @classmethod
    def items(cls, config: dict[str, Any]) -> Iterator[tuple[NestedPath, dict[str, Any]]]:
        """Every dict nested in ``config`` (the config itself excluded), with its key path."""

        def walk(value: Any, path: NestedPath) -> Iterator[tuple[NestedPath, dict[str, Any]]]:
            if isinstance(value, dict):
                yield path, value
                for key, child in value.items():
                    yield from walk(child, (*path, str(key)))
            elif isinstance(value, list):
                for child in value:
                    yield from walk(child, path)

        for key, value in config.items():
            yield from walk(value, (str(key),))

    @classmethod
    def mask(cls, config: dict[str, Any], masker: Callable[[Any], Any]) -> None:
        """Mask, in place, every nested secret field of ``config`` with ``masker``."""
        for _, item in cls.items(config):
            for field in SECRET_FIELDS & item.keys():
                item[field] = masker(item[field])

    @classmethod
    def held(cls, config: dict[str, Any]) -> bool:
        """Whether any nested item of ``config`` holds a non-empty secret value."""
        return any(
            isinstance(item.get(field), str) and item.get(field) != ""
            for _, item in cls.items(config)
            for field in SECRET_FIELDS
        )

    @staticmethod
    def label(path: NestedPath, item: dict[str, Any], field: str) -> str:
        """A human name for a nested secret, e.g. ``targets[summary].api_key``."""
        name = item.get("field")
        suffix = f"[{name}]" if isinstance(name, str) else ""
        return f"{'.'.join(path)}{suffix}.{field}"

    @staticmethod
    def effective_endpoint(item: dict[str, Any], parent_endpoint: str | None) -> str | None:
        """The endpoint a nested override calls: its own ``base_url``, else the parent's."""
        own = SecretIdentity.endpoint(item)
        return own if own is not None else parent_endpoint

    @classmethod
    def __identity(
        cls, path: NestedPath, item: dict[str, Any], parent_endpoint: str | None
    ) -> NestedIdentity:
        """The (path, field, effective endpoint) identity a nested secret belongs to."""
        return path, item.get("field"), cls.effective_endpoint(item, parent_endpoint)

    @staticmethod
    def __real(item: dict[str, Any] | None, field: str, is_masked: Callable[[Any], bool]) -> Any:
        """The live (non-empty, non-masked) secret ``field`` of a stored item, else ``None``."""
        value = item.get(field) if item is not None else None
        if isinstance(value, str) and value != "" and not is_masked(value):
            return value
        return None

    @classmethod
    def restore(
        cls,
        config: dict[str, Any],
        parent_endpoint: str | None,
        stored: dict[str, Any] | None,
        stored_endpoint: str | None,
        is_masked: Callable[[Any], bool],
    ) -> list[str]:
        """
        Resolve, in place, the masked/omitted nested secrets of an inbound config.

        A masked or omitted nested secret keeps the stored key ONLY from the stored item with the
        same identity (path, ``field``, effective endpoint). A stored key for the same path/field at
        a DIFFERENT endpoint is never carried — the caller must re-enter it. A mask with no source
        is blanked (never persisted as a live key); an explicit value is kept verbatim.

        Args:
            config (dict): The inbound node config (mutated in place).
            parent_endpoint (str | None): The inbound node's effective endpoint.
            stored (dict | None): The stored same-provider config at this node position, if any.
            stored_endpoint (str | None): The stored node's effective endpoint.
            is_masked (Callable): The redaction-marker predicate.

        Returns:
            list[str]: The nested secrets (labels) that must be re-entered.
        """
        # 1. Index the stored items by identity, and by (path, field) to detect a moved endpoint.
        by_identity: dict[NestedIdentity, dict[str, Any]] = {}
        by_name: dict[tuple[NestedPath, Any], list[dict[str, Any]]] = {}
        for path, item in cls.items(stored or {}):
            by_identity.setdefault(cls.__identity(path, item, stored_endpoint), item)
            by_name.setdefault((path, item.get("field")), []).append(item)

        # 2. Heal each inbound nested secret against its same-identity stored item.
        reentry: list[str] = []
        for path, item in cls.items(config):
            source = by_identity.get(cls.__identity(path, item, parent_endpoint))
            for field in sorted(SECRET_FIELDS):
                masked = is_masked(item.get(field))
                if not masked and field in item:
                    continue
                real = cls.__real(source, field, is_masked)
                if real is not None:
                    item[field] = real
                elif any(
                    cls.__real(other, field, is_masked) is not None
                    for other in by_name.get((path, item.get("field")), [])
                ):
                    reentry.append(cls.label(path, item, field))
                elif masked:
                    item[field] = ""
        return reentry

    @classmethod
    def foreign_inheritors(cls, config: dict[str, Any], parent_endpoint: str | None) -> list[str]:
        """
        The nested overrides relying on the parent's secret at a FOREIGN endpoint.

        A nested item with its own ``base_url`` that is not the parent's endpoint, OMITTING a secret
        the parent holds, would only work by inheriting the parent's key — which must never travel
        to another host. Such a write is refused: the caller sends the override's own secret, or
        ``""`` to call it keyless.

        Args:
            config (dict): The (healed) inbound node config.
            parent_endpoint (str | None): The node's effective endpoint (where its secret belongs).

        Returns:
            list[str]: The nested secrets (labels) that must be entered explicitly.
        """
        held = {
            field
            for field in SECRET_FIELDS
            if isinstance(config.get(field), str) and config.get(field) != ""
        }
        violations: list[str] = []
        for path, item in cls.items(config):
            own = SecretIdentity.endpoint(item)
            if own is None or own == parent_endpoint:
                continue
            violations.extend(
                cls.label(path, item, field) for field in sorted(held) if field not in item
            )
        return violations

    @classmethod
    def endpoints_with_secret(
        cls, config: dict[str, Any], parent_endpoint: str | None, field: str
    ) -> set[str]:
        """Every endpoint this config holds a live ``field`` secret for (its own and its items')."""
        endpoints: set[str] = set()
        value = config.get(field)
        if isinstance(value, str) and value != "" and parent_endpoint is not None:
            endpoints.add(parent_endpoint)
        for _, item in cls.items(config):
            own = item.get(field)
            endpoint = cls.effective_endpoint(item, parent_endpoint)
            if isinstance(own, str) and own != "" and endpoint is not None:
                endpoints.add(endpoint)
        return endpoints

    @classmethod
    def drop_inherited(cls, config: dict[str, Any], keep: set[str]) -> None:
        """
        Drop the secrets of nested items that call the parent's endpoint, outside ``keep``.

        Used when a merge MOVES the parent endpoint: a nested item without its own ``base_url``
        follows the parent to the new host, so its secret must not follow unrestated. The touched
        top-level values are deep-copied first, so a shared (current) config is never mutated.

        Args:
            config (dict): The merged node config (its affected values are replaced by copies).
            keep (set[str]): The top-level keys the caller restated (left untouched).
        """
        for key in [key for key in config if key not in keep]:
            value = copy.deepcopy(config[key])
            for _, item in cls.items({key: value}):
                if SecretIdentity.endpoint(item) is None:
                    for field in SECRET_FIELDS & item.keys():
                        item.pop(field)
            config[key] = value


__all__ = ["NestedIdentity", "NestedPath", "NestedSecrets"]
