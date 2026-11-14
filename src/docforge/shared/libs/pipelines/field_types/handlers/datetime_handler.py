# ====== Code Summary ======
# DatetimeHandler — the DATETIME FieldType: an ISO-8601 string; coercion normalises it with isoformat().

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from ..base import FieldTypeHandler


class DatetimeHandler(FieldTypeHandler):
    """DATETIME — an ISO-8601 date or date-time string."""

    field_type = FieldType.DATETIME
    expectation = "an ISO datetime string"
    json_schema = {"type": ["string", "null"], "format": "date-time"}

    def accepts(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True

    def value_error(self, field_name: str, value: Any) -> str | None:
        """Two distinct messages: not a string at all, or a string that is not ISO."""
        if not isinstance(value, str):
            return f"field '{field_name}' must be {self.expectation}"
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return f"field '{field_name}' is not a valid ISO datetime"
        return None

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> str | None:
        # Normalised ISO string — the storage layer parses it once, uniformly.
        return datetime.fromisoformat(str(value).strip()).isoformat()

    def schema_property(self, instruction: str, enum_values: list[str] | None) -> dict[str, Any]:
        """The ISO expectation must reach the MODEL, not just the schema validator."""
        return super().schema_property(f"{instruction} (ISO 8601 date-time)", enum_values)


__all__ = ["DatetimeHandler"]
