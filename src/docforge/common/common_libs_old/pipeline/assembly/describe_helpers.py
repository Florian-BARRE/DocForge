# ====== Code Summary ======
# Module-level helper functions for the UI-facing describe surface.
# Extracted from describe.py to keep pure-function helpers separate from
# the DescribeSurface mixin class.
#
# Exports:
#   _params_from_model : derive param descriptors from a Pydantic model's JSON schema
#   _param             : build a single param descriptor dict
#   _rules             : build a heading-rule list descriptor

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
from common_libs.config.pipeline import _is_secret_key

# ─── JSON-Schema scalar type → UI param type understood by the configurator ───────
_JSON_TYPE_TO_UI: dict[str, str] = {
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "string": "str",
}


def _scalar_ui_type(prop: dict[str, Any]) -> str | None:
    """
    Resolve a JSON-schema property to a scalar UI type, or None if it is not scalar-editable.

    Handles both direct scalars (``{"type": "integer"}``) and ``Optional``/union shapes that
    Pydantic emits as ``anyOf``/``oneOf`` with a ``null`` branch (``int | None`` →
    ``{"anyOf": [{"type": "integer"}, {"type": "null"}]}``). Nested-model fields (a ``$ref`` /
    an ``anyOf`` of object refs, e.g. the semantic split's ``embed`` provider config) carry no
    scalar branch and resolve to None — they are NOT editable as a single scalar control, so the
    configurator must skip them rather than render an opaque ``[object Object]`` text input.

    Args:
        prop (dict[str, Any]): A single JSON-schema property definition.

    Returns:
        str | None: The UI type tag (``int``/``float``/``bool``/``str``), or None when the field
            is a nested object / reference / array (not a scalar).
    """
    # 1. Direct scalar type
    direct = prop.get("type")
    if direct in _JSON_TYPE_TO_UI:
        return _JSON_TYPE_TO_UI[direct]
    # 2. Optional / union — pick the first scalar branch, ignoring the null branch
    for branch in (*prop.get("anyOf", []), *prop.get("oneOf", [])):
        branch_type = branch.get("type")
        if branch_type in _JSON_TYPE_TO_UI:
            return _JSON_TYPE_TO_UI[branch_type]
    # 3. No scalar type → nested object / $ref / array (not a single-control field)
    return None


def _params_from_model(model: type[BaseModel]) -> list[dict[str, Any]]:
    """
    Derive UI param descriptors from a Pydantic model's JSON schema (no hand-maintained list).

    Types, defaults, bounds (ge/le → minimum/maximum) and descriptions all come straight from
    the model, so the discovery schema can never drift from what the code actually accepts.
    Non-scalar fields (nested provider configs such as the semantic split's ``embed``) are
    skipped — they cannot be edited as a single scalar control and would otherwise render as
    ``[object Object]`` in the configurator.

    Args:
        model (type[BaseModel]): A params model (e.g. SemanticParams).

    Returns:
        list[dict[str, Any]]: Param descriptors in the configurator's shape.
    """
    schema = model.model_json_schema()
    out: list[dict[str, Any]] = []
    for name, prop in schema.get("properties", {}).items():
        ui_type = _scalar_ui_type(prop)
        if ui_type is None:
            # Nested object / $ref (e.g. semantic.embed): not scalar-editable — skip so the UI
            # never renders a broken "[object Object]" control. Its default applies on materialise.
            continue
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
