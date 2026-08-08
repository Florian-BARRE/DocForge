# ====== Code Summary ======
# Static helpers of the structgen family — the two operations a structured-generation call is built
# on: the FieldType → JSON-schema derivation (what forces the model output through structured
# generation) and the STRICT coercion of a returned value back to its contract type (a value that
# cannot be coerced is dropped, never a wrong-typed value downstream). Moved here from the metagen
# node so the generic capability owns the call+coercion; metagen calls back into these unchanged.
# They depend only on the shared vocabulary (FieldType), never on any ingest code.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType, MetadataFieldSpec

# One JSON-schema fragment per contract field type (nullable: the prompt allows honest absence).
_TYPE_SCHEMAS: dict[FieldType, dict[str, Any]] = {
    FieldType.STRING: {"type": ["string", "null"]},
    FieldType.INTEGER: {"type": ["integer", "null"]},
    FieldType.FLOAT: {"type": ["number", "null"]},
    FieldType.BOOL: {"type": ["boolean", "null"]},
    FieldType.KEYWORD_LIST: {"type": ["array", "null"], "items": {"type": "string"}},
    FieldType.DATETIME: {"type": ["string", "null"], "format": "date-time"},
    FieldType.ENUM: {"type": ["string", "null"]},  # the whitelist is injected per-spec
    FieldType.TEXT: {"type": ["string", "null"]},
    FieldType.INTEGER_LIST: {"type": ["array", "null"], "items": {"type": "integer"}},
    FieldType.FLOAT_LIST: {"type": ["array", "null"], "items": {"type": "number"}},
    FieldType.TEXT_LIST: {"type": ["array", "null"], "items": {"type": "string"}},
}


class StructGenHelpers:
    """Static utility helpers for the structgen family (schema derivation + strict coercion)."""

    logger = loggerplusplus.bind(identifier="StructGenHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StructGenHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def __coerce_enum(value: Any, enum_values: list[str] | None) -> str | None:
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

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """
        Coerce a numeric or numeric-string value to an int, only when it is integral.

        A fractional value (3.7 or "3.7") is DROPPED rather than silently truncated, matching the
        string path (where "3.7" already raises and drops) so an INTEGER field never stores a
        rounded-off number the model did not mean.

        Args:
            value (Any): The raw numeric or string value.

        Returns:
            int | None: The integral value, or None when it is fractional.

        Raises:
            ValueError: When the value is not numeric at all.
            TypeError: When the value has no numeric interpretation.
        """
        number = float(value)
        return int(number) if number.is_integer() else None

    @staticmethod
    def object_schema(fields: list[tuple[MetadataFieldSpec, str]]) -> dict[str, Any]:
        """
        Build the structured-output schema for one call — the field TYPES do the forcing.

        Args:
            fields (list[tuple[MetadataFieldSpec, str]]): The (spec, instruction) pairs the
                call must fill.

        Returns:
            dict: A strict JSON object schema (one property per field, instruction as its
            description, no extra keys allowed).
        """
        properties: dict[str, Any] = {}
        for spec, instruction in fields:
            fragment = dict(_TYPE_SCHEMAS[spec.field_type])
            # The ISO expectation must reach the MODEL, not just the schema validator.
            if spec.field_type == FieldType.DATETIME:
                instruction = f"{instruction} (ISO 8601 date-time)"
            # The whitelist IS the contract for an enum — force it in the schema itself.
            if spec.field_type == FieldType.ENUM and spec.enum_values:
                fragment["enum"] = [*spec.enum_values, None]
                instruction = f"{instruction} (one of: {', '.join(spec.enum_values)})"
            fragment["description"] = instruction
            properties[spec.field_name] = fragment
        return {
            "title": "generated_metadata",
            "description": "The requested metadata fields, extracted from the text.",
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    @classmethod
    def coerce(
        cls, value: Any, field_type: FieldType, enum_values: list[str] | None = None
    ) -> Any | None:
        """
        Coerce a model-returned value to its contract type — None when unusable.

        Args:
            value (Any): The raw value out of the structured call.
            field_type (FieldType): The contract type it must honour.
            enum_values (list[str] | None): The whitelist an ENUM value must belong to (ignored for
                every other type); an out-of-whitelist value is dropped.

        Returns:
            Any | None: The coerced value, or None (= drop the field, never store a wrong type).
        """
        # 1. An honest null is a drop, not an error.
        if value is None:
            return None
        try:
            if field_type == FieldType.STRING:
                return str(value).strip() or None
            if field_type == FieldType.INTEGER:
                return None if isinstance(value, bool) else cls._as_int(value)
            if field_type == FieldType.FLOAT:
                return float(value) if not isinstance(value, bool) else None
            if field_type == FieldType.BOOL:
                if isinstance(value, bool):
                    return value
                lowered = str(value).strip().lower()
                return {"true": True, "false": False}.get(lowered)
            if field_type in (FieldType.KEYWORD_LIST, FieldType.TEXT_LIST):
                if not isinstance(value, list):
                    return None
                keywords = [str(item).strip() for item in value if str(item).strip()]
                return keywords or None
            if field_type == FieldType.DATETIME:
                # Normalised ISO string — the storage layer parses it once, uniformly.
                return datetime.fromisoformat(str(value).strip()).isoformat()
            if field_type == FieldType.TEXT:
                return str(value).strip() or None
            if field_type == FieldType.ENUM:
                return cls.__coerce_enum(value, enum_values)
            if field_type == FieldType.INTEGER_LIST:
                if not isinstance(value, list):
                    return None
                items = [
                    coerced
                    for item in value
                    if not isinstance(item, bool) and (coerced := cls._as_int(item)) is not None
                ]
                return items or None
            if field_type == FieldType.FLOAT_LIST:
                if not isinstance(value, list):
                    return None
                numbers = [float(i) for i in value if not isinstance(i, bool)]
                return numbers or None
        except (ValueError, TypeError):
            pass
        cls.logger.debug(f"Uncoercible {field_type.value} value dropped: {value!r}")
        return None


__all__ = ["StructGenHelpers"]
