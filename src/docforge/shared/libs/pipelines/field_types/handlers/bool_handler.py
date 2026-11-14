# ====== Code Summary ======
# BoolHandler — the BOOL FieldType: a real bool; coercion also reads the strings 'true' / 'false'.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class BoolHandler(FieldTypeHandler):
    """BOOL — true / false."""

    field_type = FieldType.BOOL
    expectation = "a boolean"
    json_schema = {"type": ["boolean", "null"]}

    def accepts(self, value: Any) -> bool:
        return isinstance(value, bool)

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> bool | None:
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        return {"true": True, "false": False}.get(lowered)


__all__ = ["BoolHandler"]
