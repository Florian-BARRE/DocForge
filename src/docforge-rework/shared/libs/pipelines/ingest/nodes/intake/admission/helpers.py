# ====== Code Summary ======
# AdmissionHelpers — the pure validation rules the admit node applies against the collection contract:
# format allow-list (by extension), size cap, and the metadata checks (required user fields
# present, unknown fields per policy, value type per FieldType, enum membership). Pure functions —
# they return precise error strings; the node decides to fail.

# ====== Standard Library Imports ======
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import (
    FieldOrigin,
    FieldType,
    MetadataFieldSpec,
    UnknownFieldPolicy,
)


class AdmissionHelpers:
    """Static contract-validation rules — pure, no I/O."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AdmissionHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def extension(filename: str) -> str:
        """The lowercase extension of a filename, without the dot ('' when absent)."""
        return PurePosixPath(filename.replace("\\", "/")).suffix.lstrip(".").lower()

    @staticmethod
    def value_error(spec: MetadataFieldSpec, value: Any) -> str | None:
        """Check one declared value against its field spec (type + enum); None when valid."""
        # 1. Type check — bool is an int subclass, so exclude it from the numeric types.
        kind = spec.field_type
        if kind == FieldType.STRING and not isinstance(value, str):
            return f"field '{spec.field_name}' must be a string"
        if kind == FieldType.INTEGER and (isinstance(value, bool) or not isinstance(value, int)):
            return f"field '{spec.field_name}' must be an integer"
        if kind == FieldType.FLOAT and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            return f"field '{spec.field_name}' must be a number"
        if kind == FieldType.BOOL and not isinstance(value, bool):
            return f"field '{spec.field_name}' must be a boolean"
        if kind == FieldType.KEYWORD_LIST and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            return f"field '{spec.field_name}' must be a list of strings"
        if kind == FieldType.TEXT_LIST and (
            not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        ):
            return f"field '{spec.field_name}' must be a list of strings"
        # enum = a string whose membership is enforced by the whitelist step below.
        if kind in (FieldType.ENUM, FieldType.TEXT) and not isinstance(value, str):
            return f"field '{spec.field_name}' must be a string"
        if kind == FieldType.INTEGER_LIST and (
            not isinstance(value, list)
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in value)
        ):
            return f"field '{spec.field_name}' must be a list of integers"
        if kind == FieldType.FLOAT_LIST and (
            not isinstance(value, list)
            or not all(isinstance(i, (int, float)) and not isinstance(i, bool) for i in value)
        ):
            return f"field '{spec.field_name}' must be a list of numbers"
        if kind == FieldType.DATETIME:
            if not isinstance(value, str):
                return f"field '{spec.field_name}' must be an ISO datetime string"
            try:
                datetime.fromisoformat(value)
            except ValueError:
                return f"field '{spec.field_name}' is not a valid ISO datetime"

        # 2. Enum membership (a string value, or every item of a keyword list).
        if spec.enum_values is not None:
            items = value if isinstance(value, list) else [value]
            for item in items:
                if item not in spec.enum_values:
                    return (
                        f"field '{spec.field_name}' value {item!r} is not one of "
                        f"{spec.enum_values}"
                    )
        return None

    @classmethod
    def validate_metadata(
        cls,
        declared: dict[str, Any],
        fields: list[MetadataFieldSpec],
        policy: UnknownFieldPolicy,
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Validate the caller-declared metadata against the schema.

        Args:
            declared (dict): The metadata supplied at upload.
            fields (list[MetadataFieldSpec]): The collection's full schema.
            policy (UnknownFieldPolicy): Reject or silently drop unknown keys.

        Returns:
            tuple[dict, list[str]]: (the cleaned metadata to keep, the error messages).
        """
        errors: list[str] = []
        by_name = {spec.field_name: spec for spec in fields}

        # 1. Required USER fields must be present (system/generated are filled later — never here).
        for spec in fields:
            if spec.origin == FieldOrigin.USER and spec.required and spec.field_name not in declared:
                errors.append(f"required field '{spec.field_name}' is missing")

        # 2. Walk the declared values: unknown keys per policy, known keys type+enum checked.
        cleaned: dict[str, Any] = {}
        for name, value in declared.items():
            spec = by_name.get(name)
            if spec is None:
                if policy == UnknownFieldPolicy.REJECT:
                    errors.append(f"unknown field '{name}'")
                continue  # IGNORE → dropped
            if spec.origin != FieldOrigin.USER:
                errors.append(f"field '{name}' is {spec.origin}-filled and cannot be supplied")
                continue
            error = cls.value_error(spec, value)
            if error is not None:
                errors.append(error)
                continue
            cleaned[name] = value
        return cleaned, errors


__all__ = ["AdmissionHelpers"]
