# ====== Code Summary ======
# Static helpers of the structgen family — the two operations a structured-generation call is built
# on: the FieldType → JSON-schema derivation (what forces the model output through structured
# generation) and the STRICT coercion of a returned value back to its contract type (a value that
# cannot be coerced is dropped, never a wrong-typed value downstream). Moved here from the metagen
# node so the generic capability owns the call+coercion; metagen calls back into these unchanged.
# The per-type rules live in the FieldTypeRegistry handlers (shared_libs.pipelines.field_types); these
# helpers only route to them. They depend on the shared vocabulary, never on any ingest code.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.field_types import FieldTypeRegistry
from shared_libs.public_models import FieldType, MetadataFieldSpec


class StructGenHelpers:
    """Static utility helpers for the structgen family (schema derivation + strict coercion)."""

    logger = loggerplusplus.bind(identifier="StructGenHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StructGenHelpers is a static-only class and cannot be instantiated.")

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
            handler = FieldTypeRegistry.get(spec.field_type)
            fragment = handler.schema_property(instruction, spec.enum_values)
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
            return FieldTypeRegistry.get(field_type).coerce(value, enum_values)
        except (ValueError, TypeError):
            pass
        cls.logger.debug(f"Uncoercible {field_type.value} value dropped: {value!r}")
        return None


__all__ = ["StructGenHelpers"]
