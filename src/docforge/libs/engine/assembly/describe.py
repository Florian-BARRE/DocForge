# ====== Code Summary ======
# UI-facing describe surface for ProviderRegistry.
# Exports:
#   - _params_from_model()  : derive param descriptors from a Pydantic model's JSON schema
#   - _param()              : build a single param descriptor dict
#   - _rules()              : build a heading-rule list descriptor
#   - DescribeSurface       : mixin that adds describe_stages(), _auto_providers(), and
#                             _params_from_instance() to ProviderRegistry
#
# Keeping this surface in its own module prevents the 200-line resolution core from
# growing with every new UI descriptor tweak.  DescribeSurface is purely read-only
# relative to the registry state — it only reads self._cfg.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import _is_secret_key

if TYPE_CHECKING:
    pass

# ─── JSON-Schema scalar type → UI param type understood by the configurator ───────
_JSON_TYPE_TO_UI: dict[str, str] = {
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "string": "str",
}


def _params_from_model(model: type[BaseModel]) -> list[dict[str, Any]]:
    """
    Derive UI param descriptors from a Pydantic model's JSON schema (no hand-maintained list).

    Types, defaults, bounds (ge/le → minimum/maximum) and descriptions all come straight from
    the model, so the discovery schema can never drift from what the code actually accepts.

    Args:
        model (type[BaseModel]): A params model (e.g. SemanticParams).

    Returns:
        list[dict[str, Any]]: Param descriptors in the configurator's shape.
    """
    schema = model.model_json_schema()
    out: list[dict[str, Any]] = []
    for name, prop in schema.get("properties", {}).items():
        ui_type = _JSON_TYPE_TO_UI.get(prop.get("type", "string"), "str")
        if ui_type == "str" and _is_secret_key(name):
            ui_type = "secret"
        desc = _param(name, ui_type, prop.get("title", name), prop.get("default"), prop.get("description", ""))
        if "minimum" in prop:
            desc["min"] = prop["minimum"]
        if "maximum" in prop:
            desc["max"] = prop["maximum"]
        out.append(desc)
    return out


def _param(name: str, ptype: str, label: str, default: Any, desc: str, **extra: Any) -> dict[str, Any]:
    """
    Build a single parameter descriptor for the stage schema.

    Args:
        name (str): Dot-path key (e.g. ``"enrich.chart_to_data"``).
        ptype (str): Parameter type tag understood by the UI (``"bool"``, ``"int"``, etc.).
        label (str): Human-readable label shown in the configurator.
        default (Any): Default value pre-filled in the UI.
        desc (str): Short description shown as a tooltip.
        **extra (Any): Additional fields merged into the descriptor (e.g. ``min``, ``max``).

    Returns:
        dict[str, Any]: Parameter descriptor dict.
    """
    return {"name": name, "type": ptype, "label": label, "default": default, "description": desc, **extra}


def _rules(name: str, label: str, default: list[dict[str, Any]], desc: str) -> dict[str, Any]:
    """
    Build a list-of-(level, pattern) heading-rule editor parameter descriptor.

    Args:
        name (str): Dot-path key.
        label (str): Human-readable label.
        default (list[dict[str, Any]]): Default heading rules.
        desc (str): Tooltip description.

    Returns:
        dict[str, Any]: Parameter descriptor.
    """
    return _param(name, "rules", label, default, desc)


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
