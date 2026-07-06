# ====== Code Summary ======
# Static helpers of the metagen family: the FieldType → JSON-schema derivation (what forces the
# model output through structured generation), the auto-prompt for unbound fields, and the STRICT
# coercion of returned values back to their contract type — a value that cannot be coerced is
# dropped (never a wrong-typed value in the metadata store).

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


class MetagenHelpers:
    """Static utility helpers for the metagen family."""

    logger = loggerplusplus.bind(identifier="MetagenHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def auto_prompt(spec: MetadataFieldSpec) -> str:
        """The default per-field instruction when the config binds no prompt."""
        return f"Extract the value of '{spec.field_name}' ({spec.field_type.value}) from the text."

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
    def coerce(cls, value: Any, field_type: FieldType) -> Any | None:
        """
        Coerce a model-returned value to its contract type — None when unusable.

        Args:
            value (Any): The raw value out of the structured call.
            field_type (FieldType): The contract type it must honour.

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
                return int(value) if not isinstance(value, bool) else None
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
            if field_type in (FieldType.ENUM, FieldType.TEXT):
                return str(value).strip() or None
            if field_type == FieldType.INTEGER_LIST:
                if not isinstance(value, list):
                    return None
                items = [int(i) for i in value if not isinstance(i, bool)]
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


__all__ = ["MetagenHelpers"]
