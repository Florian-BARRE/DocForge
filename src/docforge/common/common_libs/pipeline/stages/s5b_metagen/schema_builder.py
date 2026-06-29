# ====== Code Summary ======
# MetagenSchemaBuilder — derives a STRICT JSON schema (OpenAI-Structured-Outputs-safe) from a set of
# metagen targets + their declared metadata field types. The declared field type is the single control
# surface for the output schema: string→string, number→number, keyword_list/string[]→array<string>,
# bool→boolean, date→string, enum→string{enum}. The schema is a root object with all keys required,
# additionalProperties=false, optionals expressed as ["T","null"] unions, and every unsupported
# keyword (pattern/format/min*/max*/default) omitted — so the same schema compiles + caches per scope.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec

# Field types whose generated value is a list of strings (keyword list / multi-value tag field).
_LIST_TYPES = ("string[]", "keyword_list")

# Scalar field type → JSON-schema base type. ``date`` is carried as an ISO string; ``enum`` is a
# constrained string handled separately so the allowed values can be attached.
_SCALAR_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "number": "number",
    "date": "string",
    "bool": "boolean",
    "enum": "string",
}


class MetagenSchemaBuilder:
    """
    Static builder turning metagen targets + field types into a strict JSON schema.

    One schema is built per scope-group (all chunk-scope targets share one schema; all
    document-scope targets share another) so the provider can cache the compiled grammar
    across every chunk of a document. No I/O — a pure type→schema mapping.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("MetagenSchemaBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build_json_schema(
        cls,
        targets: list[Any],
        field_types: dict[str, MetaFieldSpec],
    ) -> dict[str, Any]:
        """
        Build a strict JSON object schema covering every target with a known field type.

        Args:
            targets (list[MetaGenTarget]): The scope-group's targets (each references a field).
            field_types (dict[str, MetaFieldSpec]): Resolved type/enum lookup keyed by field name.

        Returns:
            dict: A strict JSON schema — root object, ``additionalProperties=false``, every present
                property in ``required``, optionals as ``["T","null"]`` unions. Targets whose field
                type is unknown are skipped (they are validated/blocked upstream).
        """
        # 1. One property per resolvable target; unknown fields are skipped (validated at config-apply).
        properties: dict[str, Any] = {}
        required: list[str] = []
        for target in targets:
            spec = field_types.get(target.field)
            if spec is None:
                continue
            properties[target.field] = cls._prop_for(spec)
            # OpenAI strict mode requires EVERY key in `required`; nullability is expressed via the
            # type union, not by omitting the key.
            required.append(target.field)

        # 2. Assemble the strict root object (no extra keys, no unsupported keywords).
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @classmethod
    def _prop_for(cls, spec: MetaFieldSpec) -> dict[str, Any]:
        """
        Build the JSON-schema property for one field spec (type-driven, strict-safe).

        Args:
            spec (MetaFieldSpec): The generated field's declared type/enum/required.

        Returns:
            dict: The property schema. A non-required field is made nullable via a ``["T","null"]``
                type union (the key still stays in the parent's ``required`` list).
        """
        nullable = not spec.required

        # 1. List-valued fields → array of strings.
        if spec.field_type in _LIST_TYPES:
            prop: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
            if nullable:
                prop["type"] = ["array", "null"]
            return prop

        # 2. Enum → constrained string carrying its allowed values.
        if spec.field_type == "enum":
            prop = {"type": "string", "enum": list(spec.enum_values or [])}
            if nullable:
                prop["type"] = ["string", "null"]
            return prop

        # 3. Remaining scalars (string / number / date / bool).
        base = _SCALAR_TYPE_MAP.get(spec.field_type, "string")
        prop = {"type": [base, "null"] if nullable else base}
        return prop


__all__ = ["MetagenSchemaBuilder"]
