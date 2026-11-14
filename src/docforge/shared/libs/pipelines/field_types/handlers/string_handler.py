# ====== Code Summary ======
# StringHandler — the STRING FieldType: any str is valid; coercion strips it and drops the empty result.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class StringHandler(FieldTypeHandler):
    """STRING — a short string value."""

    field_type = FieldType.STRING
    expectation = "a string"
    json_schema = {"type": ["string", "null"]}

    def accepts(self, value: Any) -> bool:
        return isinstance(value, str)

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> str | None:
        return str(value).strip() or None


__all__ = ["StringHandler"]
