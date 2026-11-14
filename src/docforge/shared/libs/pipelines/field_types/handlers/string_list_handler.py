# ====== Code Summary ======
# StringListHandler — shared rules of the string-list FieldTypes (KEYWORD_LIST, TEXT_LIST): a list of str; coercion strips every item and drops the empties.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class StringListHandler(FieldTypeHandler):
    """Base of the list-of-strings types (the concrete subclass sets ``field_type``)."""

    expectation = "a list of strings"
    json_schema = {"type": ["array", "null"], "items": {"type": "string"}}

    def accepts(self, value: Any) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> list[str] | None:
        if not isinstance(value, list):
            return None
        keywords = [str(item).strip() for item in value if str(item).strip()]
        return keywords or None


__all__ = ["StringListHandler"]
