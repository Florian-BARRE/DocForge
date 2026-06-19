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
from libs.core.contracts.pipeline_config import _is_secret_key

# ====== Local Project Imports ======
from .describe_helpers import _param, _params_from_model, _rules  # noqa: F401 (re-exported)


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
            value = getattr(instance, name, None)
            is_secret = _is_secret_key(name)
            ftype = field_schema.get("type", "string")
            ui_type = (
                "secret" if is_secret
                else "bool" if ftype == "boolean"
                else "float" if ftype == "number"
                else "int" if ftype == "integer"
                else "str"
            )
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
        from libs.core.contracts._registry import get_configs

        providers = []
        for config_cls in get_configs(category).values():
            available, note = config_cls.availability(self._cfg)  # type: ignore[attr-defined]
            instance = config_cls().merge_defaults(self._cfg)  # type: ignore[attr-defined]
            providers.append({
                "id": config_cls.model_fields["id"].default,
                "label": getattr(config_cls, "_label", config_cls.__name__),
                "available": available,
                "selectable": True,
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
        from libs.core.contracts._registry import auto_import

        for pkg in (
            "libs.capabilities.converter",
            "libs.capabilities.parser",
            "libs.capabilities.classifier",
            "libs.capabilities.ocr",
            "libs.capabilities.vlm",
            "libs.capabilities.embed",
        ):
            auto_import(pkg)
        # split_method configs live in params.py, imported via chunking __init__
        import libs.engine.stages.chunking as _chunking_pkg  # noqa: F401

        # 2. Build and return the full stage descriptor list
        return {
            "stages": [
                {
                    "id": "s0", "label": "S0 · INGEST", "name": "INGEST",
                    "description": "blake3 fingerprint + SHA-256 dedup + S3 upload.",
                    "params": [], "groups": [],
                },
                {
                    "id": "s1", "label": "S1 · PARSE", "name": "PARSE",
                    "description": "Convert + parse the document into the canonical IR block tree.",
                    "params": [
                        {"name": "parse.gate.min_score", "label": "Parse gate — min_score", "type": "float",
                         "default": 0.5, "description": "Escalate when the parser's quality score is below this."},
                    ],
                    "groups": [
                        {"key": "parse.chain", "kind": "multi", "capability": "parse",
                         "label": "Parser chain (escalation order)",
                         "providers": self._auto_providers("parser", "multi")},
                    ],
                },
                {
                    "id": "s2", "label": "S2 · ENRICH", "name": "ENRICH",
                    "description": "Classify figures, then route to OCR / VLM / chart-to-data.",
                    "params": [
                        {"name": "enrich.chart_to_data", "label": "Chart → data", "type": "bool",
                         "default": False, "description": "Extract chart series into a structured table"},
                        {"name": "enrich.max_budget_usd", "label": "Max budget (USD)", "type": "float",
                         "default": 0.0, "description": "Per-job spend cap; 0 = no limit"},
                        {"name": "enrich.classifier_gate.min_score", "label": "Classifier gate — min_score",
                         "type": "float", "default": 0.5,
                         "description": "Escalate the classifier chain below this confidence."},
                        {"name": "enrich.ocr_gate.min_score", "label": "OCR gate — min_score",
                         "type": "float", "default": 0.85,
                         "description": "Escalate the OCR chain below this confidence."},
                        {"name": "enrich.vlm_gate.min_score", "label": "VLM gate — min_score",
                         "type": "float", "default": 0.5,
                         "description": "Escalate the VLM chain below this quality score."},
                    ],
                    "groups": [
                        {"key": "enrich.classifier_chain", "kind": "multi", "capability": "classifier",
                         "label": "Figure classifier chain (escalation order)",
                         "providers": self._auto_providers("classifier", "multi")},
                        {"key": "enrich.ocr_chain", "kind": "multi", "capability": "ocr",
                         "label": "OCR chain (escalation order)",
                         "providers": self._auto_providers("ocr", "multi")},
                        {"key": "enrich.vlm_chain", "kind": "multi", "capability": "vlm",
                         "label": "VLM chain (escalation order; empty = disabled)",
                         "providers": self._auto_providers("vlm", "multi")},
                    ],
                },
                {
                    "id": "s4", "label": "S4 · CHUNK", "name": "CHUNK",
                    "description": "Structure-aware chunking: heading skeleton + configurable intra-section split.",
                    "params": [
                        {"name": "chunk.reinject_breadcrumb", "label": "Reinject breadcrumb", "type": "bool",
                         "default": True, "description": "Prepend section path to embed_text"},
                        {"name": "chunk.merge_short_sections", "label": "Merge short sections", "type": "bool",
                         "default": True, "description": "Fold heading-only / tiny sections into neighbours"},
                        {"name": "chunk.hierarchical", "label": "Hierarchical chunks", "type": "bool",
                         "default": False, "description": "Emit a parent chunk per section over its children"},
                        {"name": "chunk.cross_references", "label": "Cross-references", "type": "bool",
                         "default": True, "description": "Detect see Figure/Article links between chunks"},
                    ],
                    "groups": [
                        {"key": "chunk.split_method", "kind": "single", "capability": "split_method",
                         "label": "Intra-section split method",
                         "providers": self._auto_providers("split_method", "single")},
                    ],
                },
                {
                    "id": "s5", "label": "S5 · CONTEXTUALIZE", "name": "CONTEXTUALIZE",
                    "description": (
                        "Build each chunk's embed_text header (doc title + heading "
                        "breadcrumb) before S6 embedding."
                    ),
                    "params": [
                        {"name": "contextualize.include_doc_title", "type": "bool", "default": True,
                         "label": "Include document title",
                         "description": "Prepend DocumentIR.title to the header unless it is already the first breadcrumb."},
                        {"name": "contextualize.include_breadcrumb", "type": "bool", "default": True,
                         "label": "Include heading breadcrumb",
                         "description": "Include the H1 > H2 > H3 trail in the header."},
                        {"name": "contextualize.breadcrumb_separator", "type": "str", "default": " > ",
                         "label": "Breadcrumb separator",
                         "description": "Joins title + breadcrumb segments (e.g. ' > ', ' / ', '\\n')."},
                        {"name": "contextualize.header_body_separator", "type": "str", "default": "\n\n",
                         "label": "Header / body separator",
                         "description": "Joins the header line to the chunk body (default = blank line)."},
                    ],
                    "groups": [],
                },
                {
                    "id": "s6", "label": "S6 · EMBED", "name": "EMBED",
                    "description": "Embed chunks and upsert multi-vector points into Qdrant.",
                    "params": [
                        {"name": "embed.gate.min_score", "label": "Embed gate — min_score", "type": "float",
                         "default": 0.5,
                         "description": "Escalate the embedding chain if a provider falls below this score."},
                    ],
                    "groups": [
                        {"key": "embed.chain", "kind": "multi", "capability": "embed",
                         "label": "Embedding chain (escalation order)",
                         "providers": self._auto_providers("embed", "multi")},
                    ],
                },
            ]
        }
