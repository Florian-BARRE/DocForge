# ====== Code Summary ======
# Small pure helper for the config describer: map a JSON-schema scalar property to the UI scalar type
# the configurator understands, or None when the field is not a single-control scalar (a nested
# object / $ref / array). Extracted so the recursive describer stays focused on tree assembly.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

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
    ``{"anyOf": [{"type": "integer"}, {"type": "null"}]}``). Nested-model fields (a ``$ref`` / an
    ``anyOf`` of object refs) carry no scalar branch and resolve to None — they are NOT editable as
    a single scalar control, so the configurator must skip them rather than render an opaque input.

    Args:
        prop (dict[str, Any]): A single JSON-schema property definition.

    Returns:
        str | None: The UI type tag (``int``/``float``/``bool``/``str``), or None when the field is
            a nested object / reference / array (not a scalar).
    """
    # 1. Direct scalar type.
    direct = prop.get("type")
    if direct in _JSON_TYPE_TO_UI:
        return _JSON_TYPE_TO_UI[direct]
    # 2. Optional / union — pick the first scalar branch, ignoring the null branch.
    for branch in (*prop.get("anyOf", []), *prop.get("oneOf", [])):
        branch_type = branch.get("type")
        if branch_type in _JSON_TYPE_TO_UI:
            return _JSON_TYPE_TO_UI[branch_type]
    # 3. No scalar type → nested object / $ref / array (not a single-control field).
    return None


__all__ = ["_scalar_ui_type"]
