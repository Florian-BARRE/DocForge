# ====== Code Summary ======
# FloatListHandler — the FLOAT_LIST FieldType: a list of real numbers; coercion floats every non-bool item.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class FloatListHandler(FieldTypeHandler):
    """FLOAT_LIST — a list of numbers (Qdrant matches any element)."""

    field_type = FieldType.FLOAT_LIST
    expectation = "a list of numbers"
    json_schema = {"type": ["array", "null"], "items": {"type": "number"}}

    def accepts(self, value: Any) -> bool:
        return isinstance(value, list) and all(
            isinstance(i, (int, float)) and not isinstance(i, bool) for i in value
        )

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> list[float] | None:
        if not isinstance(value, list):
            return None
        numbers = [float(i) for i in value if not isinstance(i, bool)]
        return numbers or None


__all__ = ["FloatListHandler"]
