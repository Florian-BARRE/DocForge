# ====== Code Summary ======
# UI-facing describe surface for ProviderRegistry.
# Exports:
#   - DescribeSurface: mixin that adds describe_stages(), _auto_providers(), and
#                      _params_from_instance() to ProviderRegistry
#
# Module-level helper functions (_params_from_model, _param, _rules) live in
# describe_helpers.py and are imported here for backward compatibility.
#
# Keeping this surface in its own module prevents the 200-line resolution core from
# growing with every new UI descriptor tweak.  DescribeSurface is purely read-only
# relative to the registry state — it only reads self._cfg.
#
# Design note: describe_stages() is a monolithic return dict spanning ~100 lines
# because each stage descriptor is a deeply nested dict literal — extracting it
# further would create artificial seams with no structural gain.  This is a
# documented exception to the 200-line guideline for this module.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import _is_secret_key

# ====== Local Project Imports ======
from .describe_helpers import _param, _params_from_model, _rules, _scalar_ui_type  # noqa: F401 (re-exported)
from .stage_descriptors import StageDescriptorHelpers


class DescribeSurface:
    """
    Mixin that adds the UI-facing describe surface to ProviderRegistry.

    Methods here are read-only relative to registry state — they query provider configs
    and availability but never mutate any internal registry attribute.  DescribeSurface
    expects the host class to expose ``self._cfg`` (the RUNTIME_CONFIG instance).
    """

    # ─── Instance-based schema builders ─────────────────────────────────────────

    @staticmethod
    def _params_from_instance(instance: Any) -> list[dict]:
        """
        Build the UI param schema list from a pre-filled Config instance.

        Uses the JSON schema for field types and the instance values for defaults,
        masking secrets.  Excludes the 'id' discriminator field.

        Args:
            instance (Any): A Config BaseModel instance with deployment defaults merged.

        Returns:
            list[dict]: Param descriptors for the playground UI.
        """
        schema = instance.__class__.model_json_schema()
        result = []
        for name, field_schema in schema.get("properties", {}).items():
            if name == "id":
                continue
            # Skip non-scalar fields (nested provider configs such as the semantic split's
            # ``embed``): they cannot be edited as a single control and would otherwise render
            # as "[object Object]" in the configurator. _scalar_ui_type handles Optional unions.
            scalar_type = _scalar_ui_type(field_schema)
            if scalar_type is None:
                continue
            value = getattr(instance, name, None)
            is_secret = _is_secret_key(name)
            ui_type = "secret" if is_secret else scalar_type
            result.append({
                "name": name,
                "label": field_schema.get("description", name.replace("_", " ").title()),
                "type": ui_type,
                "default": ("•••" if is_secret and value else value),
                "note": "",
            })
        return result

    def _auto_providers(self, category: str, kind: str = "single") -> list[dict]:
        """
        Build the stage group descriptor for a provider category using the auto-registry.

        Iterates all registered Config classes for the category, calls availability()
        and merge_defaults() on each to derive the full provider descriptor with
        deployment-specific defaults pre-filled.

        Args:
            category (str): Provider registry category key (e.g. "ocr", "vlm").
            kind (str): "single", "multi", or "optional" — passed to the UI group.

        Returns:
            list[dict]: Provider descriptors ready for the stage group's "providers" list.
        """
        from common_libs.config.pipeline._registry import get_configs

        providers = []
        for config_cls in get_configs(category).values():
            available, note = config_cls.availability(self._cfg)  # type: ignore[attr-defined]
            instance = config_cls().merge_defaults(self._cfg)  # type: ignore[attr-defined]
            # A provider is selectable unless it opts out via an optional `selectable` hook.
            # Most providers are always selectable (their `available` flag merely reflects a
            # reachable service); some (e.g. vit_onnx) require per-collection configuration and
            # must NOT be offered as a pickable choice until that config exists.
            selectable_hook = getattr(config_cls, "selectable", None)
            selectable = bool(selectable_hook(self._cfg)) if callable(selectable_hook) else True
            providers.append({
                "id": config_cls.model_fields["id"].default,
                "label": getattr(config_cls, "_label", config_cls.__name__),
                "available": available,
                "selectable": selectable,
                "note": note,
                "params": self._params_from_instance(instance),
            })
        return providers

    def describe_stages(self) -> dict[str, Any]:
        """
        Describe every pipeline stage: its tunable params and selectable providers.

        Fully auto-derived from the provider registry — no hardcoded provider IDs.
        Adding a new provider auto-appears here the next time this method is called.

        Returns:
            dict: {"stages": [StageSchema, ...]} — each stage lists its groups and providers.
        """
        # 1. Trigger auto-import for all categories so @register decorators fire
        from common_libs.config.pipeline._registry import auto_import

        for pkg in (
            "libs.providers.converter",
            "libs.providers.parser",
            "libs.providers.classifier",
            "libs.providers.ocr",
            "libs.providers.vlm",
            "libs.providers.embed",
        ):
            auto_import(pkg)
        # split_method configs live in params.py, imported via chunking __init__
        import common_libs.pipeline.stages.s4_chunk as _chunking_pkg  # noqa: F401

        # 2. Build and return the full stage descriptor list (nested dict literals live in
        # StageDescriptorHelpers; provider lists come from this registry's _auto_providers).
        return StageDescriptorHelpers.build(self._auto_providers)
