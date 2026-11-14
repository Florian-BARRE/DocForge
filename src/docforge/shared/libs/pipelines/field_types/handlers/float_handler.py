# ====== Code Summary ======
# FloatHandler — the FLOAT FieldType: an int or float (a bool is not a number); coercion is float().

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class FloatHandler(FieldTypeHandler):
    """FLOAT — any real number."""

    field_type = FieldType.FLOAT
    expectation = "a number"
    json_schema = {"type": ["number", "null"]}

    def accepts(self, value: Any) -> bool:
        return not isinstance(value, bool) and isinstance(value, (int, float))

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> float | None:
        return float(value) if not isinstance(value, bool) else None


__all__ = ["FloatHandler"]
