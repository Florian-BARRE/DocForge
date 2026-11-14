# ====== Code Summary ======
# IntegerListHandler — the INTEGER_LIST FieldType: a list of real ints; coercion keeps the integral items.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler
from .integer_handler import IntegerHandler


class IntegerListHandler(FieldTypeHandler):
    """INTEGER_LIST — a list of integers (Qdrant matches any element)."""

    field_type = FieldType.INTEGER_LIST
    expectation = "a list of integers"
    json_schema = {"type": ["array", "null"], "items": {"type": "integer"}}

    def accepts(self, value: Any) -> bool:
        return isinstance(value, list) and all(
            isinstance(i, int) and not isinstance(i, bool) for i in value
        )

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> list[int] | None:
        if not isinstance(value, list):
            return None
        items = [
            coerced
            for item in value
            if not isinstance(item, bool) and (coerced := IntegerHandler.as_int(item)) is not None
        ]
        return items or None


__all__ = ["IntegerListHandler"]
