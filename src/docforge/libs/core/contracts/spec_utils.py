# ====== Code Summary ======
# Shared backward-compat helper for flattening old {id, params} ProviderSpec dicts into the
# flat format that each typed discriminated-union Config model expects.  Every provider Config
# that uses a model_validator(mode="before") imports this function instead of defining its own
# private copy, eliminating the duplication that existed across ~13 capability files.
#
# ProviderSpecHelpers wraps the logic as a static-only class. The module-level
# flatten_provider_spec function is preserved as a thin wrapper for backward compat.

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

            {"id": "tei", "params": {"base_url": "http://tei:8080"}}

        Typed union members (Pydantic v2) expect the flat form::

            {"id": "tei", "base_url": "http://tei:8080"}

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


# ── Module-level alias — keep flatten_provider_spec importable at the same path ──
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
