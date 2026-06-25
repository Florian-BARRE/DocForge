# ====== Code Summary ======
# Shared backward-compat helpers for provider specs:
#  - flatten_provider_spec: flatten old {id, params} DB rows into the flat form each typed
#    discriminated-union Config model expects.
#  - normalize_legacy_id: rewrite a removed/legacy provider id to its canonical replacement
#    (e.g. embed tei -> bge_server, rerank bge_reranker -> bge_server) BEFORE the union dispatch.
# Every provider Config that uses a model_validator(mode="before") imports these instead of
# defining private copies, eliminating duplication across the capability files.
#
# ProviderSpecHelpers wraps the logic as a static-only class. Module-level thin wrappers are
# preserved so existing imports keep working.

# ====== Standard Library Imports ======
from typing import Any


class ProviderSpecHelpers:
    """
    Static-only helper class for ProviderSpec backward-compat normalization.

    Provides ``flatten_provider_spec`` to convert old ``{id, params}`` DB rows
    to the flat form expected by typed discriminated-union configs.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def flatten_provider_spec(v: Any) -> Any:
        """
        Flatten an old-style ``{id, params}`` ProviderSpec dict into the flat form expected
        by typed discriminated-union configs.

        Old DB rows store provider configs as::

            {"id": "tei", "params": {"base_url": "http://bge_server:80"}}

        Typed union members (Pydantic v2) expect the flat form::

            {"id": "tei", "base_url": "http://bge_server:80"}

        This function is called from ``model_validator(mode="before")`` in each sub-config
        class so that existing stored configs deserialise correctly after the migration to
        typed unions.

        Args:
            v (Any): Raw value arriving at the validator (dict or already-parsed model).

        Returns:
            Any: Flattened dict when ``v`` is an old-style ``{id, params}`` dict;
                 ``v`` unchanged in every other case.
        """
        # Flatten only when the value is an {id, params} dict — leave all other shapes intact.
        if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
            return {"id": v.get("id"), **v["params"]}
        return v

    @staticmethod
    def normalize_legacy_id(v: Any, aliases: dict[str, str]) -> Any:
        """
        Rewrite a provider spec's discriminator from a removed/legacy id to its replacement.

        When a provider CHOICE is removed because a newer provider subsumes it (same HTTP
        contract, same compatible fields), stored pipelines may still carry the old ``id``.
        Validating such a spec against the current discriminated union would fail. This helper
        is called from ``model_validator(mode="before")`` to swap only the discriminator, so the
        compatible fields carry over and any extra field the replacement adds falls back to its
        own default.

        Current aliases (defined by each caller): embed ``tei`` -> ``bge_server`` and rerank
        ``bge_reranker`` -> ``bge_server`` — the off-the-shelf TEI image was replaced by the local
        bge_server host, which speaks the same TEI HTTP contract for both embed and rerank.

        Args:
            v (Any): A single provider spec (dict) or any other value.
            aliases (dict[str, str]): Mapping of legacy id -> canonical replacement id.

        Returns:
            Any: The spec with a rewritten ``id`` when it is a known legacy alias; otherwise
                 ``v`` unchanged.
        """
        # Only dicts carry a discriminator to rewrite; leave already-parsed models untouched.
        if isinstance(v, dict) and v.get("id") in aliases:
            return {**v, "id": aliases[v["id"]]}
        return v


# ── Module-level aliases — keep these importable at the same path (back-compat) ──
def flatten_provider_spec(v: Any) -> Any:
    """
    Flatten an old-style ``{id, params}`` ProviderSpec dict into the flat form.

    Thin wrapper around ``ProviderSpecHelpers.flatten_provider_spec``.
    Preserved for backward compat — all existing imports continue to work.

    Args:
        v (Any): Raw value arriving at the validator.

    Returns:
        Any: Flattened dict or ``v`` unchanged.
    """
    return ProviderSpecHelpers.flatten_provider_spec(v)


def normalize_legacy_id(v: Any, aliases: dict[str, str]) -> Any:
    """
    Rewrite a provider spec's legacy discriminator to its replacement.

    Thin wrapper around ``ProviderSpecHelpers.normalize_legacy_id``.

    Args:
        v (Any): A single provider spec (dict) or any other value.
        aliases (dict[str, str]): Mapping of legacy id -> canonical replacement id.

    Returns:
        Any: The spec with a rewritten ``id`` when it is a known legacy alias; otherwise unchanged.
    """
    return ProviderSpecHelpers.normalize_legacy_id(v, aliases)


__all__ = ["ProviderSpecHelpers", "flatten_provider_spec", "normalize_legacy_id"]
