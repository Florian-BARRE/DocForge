# ====== Code Summary ======
# EmbedProviderRegistry — the kind → provider-class table the embed node's dense/sparse slots are
# validated and built against. A provider class self-registers with a decorator (like a graph node),
# declaring the axes it serves, so adding a sparse server (SPLADE, a TEI sparse endpoint…) is ONE new
# provider class: the slot validation, the stage-rail choice lists and the capabilities matrix all
# read this table.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from .base import EmbedAxis, EmbedProvider, EmbedProviderConfig


class EmbedProviderRegistry:
    """Static registry of the embed slot providers, keyed by kind."""

    __PROVIDERS: dict[str, type[EmbedProvider]] = {}

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EmbedProviderRegistry is a static-only class and cannot be instantiated.")

    @classmethod
    def register(cls, provider: type[EmbedProvider]) -> type[EmbedProvider]:
        """Register a provider class under its KIND (decorator)."""
        cls.__PROVIDERS[provider.KIND] = provider
        return provider

    @classmethod
    def get(cls, kind: str) -> type[EmbedProvider]:
        """
        Return the provider class of a kind.

        Raises:
            KeyError: When no provider is registered under that kind.
        """
        if kind not in cls.__PROVIDERS:
            raise KeyError(f"unknown embed provider '{kind}' (known: {sorted(cls.__PROVIDERS)})")
        return cls.__PROVIDERS[kind]

    @classmethod
    def kinds(cls, axis: EmbedAxis) -> list[str]:
        """The provider kinds serving an axis, sorted (the slot's choice list)."""
        return sorted(kind for kind, provider in cls.__PROVIDERS.items() if axis in provider.AXES)

    @classmethod
    def validate(cls, axis: EmbedAxis, value: Any) -> EmbedProviderConfig:
        """
        Validate a slot value against its kind's config class (extra="forbid" applies).

        Args:
            axis (EmbedAxis): The slot being validated (the kind must serve it).
            value (Any): A slot dict carrying ``kind``, or an already-validated config.

        Returns:
            EmbedProviderConfig: The kind's typed config.

        Raises:
            ValueError: When the kind is missing, unknown, or does not serve the axis.
        """
        if isinstance(value, EmbedProviderConfig):
            value = value.model_dump()
        if not isinstance(value, dict) or not value.get("kind"):
            raise ValueError(f"the {axis} slot needs a provider 'kind'")
        kind = value["kind"]
        if kind not in cls.__PROVIDERS:
            raise ValueError(f"unknown {axis} provider '{kind}' (known: {cls.kinds(axis)})")
        provider = cls.__PROVIDERS[kind]
        if axis not in provider.AXES:
            raise ValueError(f"provider '{kind}' has no {axis} axis (choose: {cls.kinds(axis)})")
        return provider.Config.model_validate(value)

    @classmethod
    def build(cls, config: EmbedProviderConfig) -> EmbedProvider:
        """Instantiate the provider of a validated slot config."""
        return cls.get(config.kind)(config)

    @classmethod
    def config_schemas(cls, axis: EmbedAxis) -> dict[str, dict]:
        """The JSON schema of every provider config serving an axis — the slot form per kind."""
        return {kind: cls.get(kind).Config.model_json_schema() for kind in cls.kinds(axis)}


__all__ = ["EmbedProviderRegistry"]
