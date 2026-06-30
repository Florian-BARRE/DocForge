# ====== Code Summary ======
# ProviderCatalog — the app-side replacement for the removed common ProviderRegistry's catalog
# surface. The node-engine rewrite dropped ProviderRegistry; the FastAPI app still needs two
# read-only catalog views derived from the @register provider-config registry:
#   * ensure_registered() — idempotently fire every provider category's @register decorators (so
#     get_configs(category) is populated) and register the three chunk split-method configs under
#     "split_method" (these are plain co-located configs in the pipelines layer, NOT @register-
#     decorated, so the app registers them itself to keep the discovery/validation catalog complete).
#   * describe_stages() — flatten the catalog into the {"stages": [...]} shape ConfigValidator's
#     ProviderChecks.build_provider_index consumes, so per-collection config can still be validated
#     against the live provider catalog before any spend.
#
# I/O-FREE BY CONTRACT: this is a config-form / validation catalog, NOT a monitoring surface. It does
# NO network probing — every choice reports ``available=True`` and only the cheap, non-I/O
# ``selectable()`` hook gates a provider. Whether a service is currently reachable is owned by
# /monitoring/resources. (This mirrors the recursive config_describer's stance and avoids the ~1s
# socket probe per provider that made the old probing describe_stages take tens of seconds.)

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import auto_import, get_configs, register

# Provider categories whose @register decorators must have fired before the catalog is read. The
# canonical package root is ``common_libs.providers.*``. llm + rerank are included (search-only) so
# the recursive config_describer's nested SearchConfig unions resolve too.
_AUTO_IMPORT_PACKAGES: tuple[str, ...] = (
    "common_libs.providers.converter",
    "common_libs.providers.parser",
    "common_libs.providers.classifier",
    "common_libs.providers.ocr",
    "common_libs.providers.vlm",
    "common_libs.providers.embed",
    "common_libs.providers.rerank",
    "common_libs.providers.llm",
)

# ProviderChecks capability → @register registry category. The capability keys are exactly the ones
# ProviderChecks._check_one looks up (note "parse"/"split_method" differ from the registry category
# "parser"/"split_method"); the value is the registry category get_configs() reads.
_CAPABILITY_CATEGORY: dict[str, str] = {
    "parse": "parser",
    "split_method": "split_method",
    "classifier": "classifier",
    "ocr": "ocr",
    "vlm": "vlm",
    "embed": "embed",
}

# Each capability grouped under the ingest stage that owns it (mirrors the pipeline order). Only the
# groups/providers are read by the validator; the stage key is purely informational.
_STAGE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("parse", ("parse",)),
    ("chunk", ("split_method",)),
    ("enrich", ("classifier", "ocr", "vlm")),
    ("embed", ("embed",)),
)


class ProviderCatalog:
    """
    Static-only catalog views over the @register provider-config registry (no instance state).

    Read-only relative to all state apart from the one-time, idempotent registration bootstrap; it
    performs NO network I/O.
    """

    _registered: bool = False

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only catalog."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @classmethod
    def ensure_registered(cls) -> None:
        """
        Populate the provider registry once per process (idempotent, filesystem-cheap thereafter).

        ``@register`` is a permanent, process-global side effect of importing a provider module, so
        re-walking the packages on every describe call is pure waste; the guard collapses it to a
        single first walk. The chunk split-method configs are registered here too (they are not
        ``@register``-decorated in the pipelines layer).
        """
        # 1. Already bootstrapped in this process → the registry is permanent, nothing to do.
        if cls._registered:
            return
        # 2. Fire every provider category's @register decorators.
        for package in _AUTO_IMPORT_PACKAGES:
            auto_import(package)
        # 3. Register the three chunk split-method configs under "split_method" (plain co-located
        #    configs in the pipelines layer — the app registers them so the catalog is complete).
        cls.__register_split_methods()
        cls._registered = True

    @staticmethod
    def __register_split_methods() -> None:
        """Register the chunk split-method config classes under the "split_method" category."""
        # 1. Already registered (e.g. a prior ensure_registered) → idempotent no-op.
        if get_configs("split_method"):
            return
        # 2. Import the co-located split-method configs (read-only import of the pipelines layer)
        #    and register each under "split_method" so get_configs() exposes them as choices.
        from common_libs.pipelines.core.ingest.stages.chunk.config import (
            IngestStageChunkSplitSemanticConfig,
            IngestStageChunkSplitSentenceWindowConfig,
            IngestStageChunkSplitTokenBudgetConfig,
        )

        for config_cls in (
            IngestStageChunkSplitTokenBudgetConfig,
            IngestStageChunkSplitSentenceWindowConfig,
            IngestStageChunkSplitSemanticConfig,
        ):
            register("split_method")(config_cls)

    @classmethod
    def describe_stages(cls) -> dict[str, list[dict[str, Any]]]:
        """
        Flatten the provider catalog into the ``{"stages": [...]}`` shape the validator consumes.

        Returns:
            dict: ``{"stages": [{"key", "groups": [{"capability", "providers": [...]}]}]}`` where
                each provider is ``{"id", "label", "selectable", "available", "note"}``. ``available``
                is always True (config-form stance; liveness is a /monitoring concern).
        """
        # 1. Make sure every category is registered before reading it.
        cls.ensure_registered()

        # 2. Build one stage per pipeline group, each with its capability provider groups.
        stages: list[dict[str, Any]] = []
        for stage_key, capabilities in _STAGE_GROUPS:
            groups = [cls.__group(capability) for capability in capabilities]
            stages.append({"key": stage_key, "groups": groups})
        return {"stages": stages}

    @classmethod
    def __group(cls, capability: str) -> dict[str, Any]:
        """Build one capability group dict (capability + its provider choices) for describe_stages."""
        category = _CAPABILITY_CATEGORY[capability]
        providers = [cls.__provider(config_cls) for config_cls in get_configs(category).values()]
        return {"capability": capability, "providers": providers}

    @classmethod
    def __provider(cls, config_cls: type) -> dict[str, Any]:
        """Project one provider config class into a validator-shaped provider descriptor dict."""
        return {
            "id": config_cls.model_fields["id"].default,
            "label": getattr(config_cls, "_label", config_cls.__name__),
            # Config-form catalog: never live-probed. UP/DOWN is a /monitoring/resources concern.
            "available": True,
            "selectable": cls.__selectable(config_cls),
            "note": "",
        }

    @staticmethod
    def __selectable(config_cls: type) -> bool:
        """Honor the optional ``selectable(cfg)`` hook (most providers are always selectable)."""
        hook = getattr(config_cls, "selectable", None)
        if not callable(hook):
            return True
        try:
            return bool(hook(None))
        except Exception:
            return False


def describe_stages() -> dict[str, list[dict[str, Any]]]:
    """
    Return the live provider stage schema consumed by ConfigValidator (module-level entry point).

    Returns:
        dict: ``{"stages": [...]}`` — see :meth:`ProviderCatalog.describe_stages`.
    """
    return ProviderCatalog.describe_stages()


def ensure_registered() -> None:
    """Populate the provider registry once per process (module-level entry point)."""
    ProviderCatalog.ensure_registered()


__all__ = ["ProviderCatalog", "describe_stages", "ensure_registered"]
