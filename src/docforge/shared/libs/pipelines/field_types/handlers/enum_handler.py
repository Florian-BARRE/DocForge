# ====== Code Summary ======
# EnumHandler — the ENUM FieldType: a string whose membership is enforced by the whitelist; coercion matches it case-insensitively and keeps the DECLARED casing.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType

# ====== Local Project Imports ======
from .string_handler import StringHandler


class EnumHandler(StringHandler):
    """ENUM — a string constrained to the field's enum_values."""

    field_type = FieldType.ENUM
    json_schema = {"type": ["string", "null"]}  # the whitelist is injected per-spec

    def coerce(self, value: Any, enum_values: list[str] | None = None) -> str | None:
        """
        Coerce a value to an ENUM member — an out-of-whitelist value is dropped.

        Membership is the contract for an enum: a label the model invented (not in the field's
        whitelist) is DROPPED rather than stored as a silently wrong value. Matching is
        case-insensitive but the DECLARED casing is what survives. With no declared whitelist the
        stripped string passes through unchanged (nothing to validate against).

        Args:
            value (Any): The raw model value.
            enum_values (list[str] | None): The field's allowed values (the whitelist).

        Returns:
            str | None: The matching declared value, or None when empty or out of the whitelist.
        """
        text = str(value).strip()
        if not text:
            return None
        if not enum_values:
            return text
        for candidate in enum_values:
            if candidate.strip().lower() == text.lower():
                return candidate
        return None

    def schema_property(self, instruction: str, enum_values: list[str] | None) -> dict[str, Any]:
        """The whitelist IS the contract for an enum — force it in the schema itself."""
        fragment = dict(self.json_schema)
        if enum_values:
            fragment["enum"] = [*enum_values, None]
            instruction = f"{instruction} (one of: {', '.join(enum_values)})"
        fragment["description"] = instruction
        return fragment


__all__ = ["EnumHandler"]
