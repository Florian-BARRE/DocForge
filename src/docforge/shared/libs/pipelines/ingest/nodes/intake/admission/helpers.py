# ====== Code Summary ======
# AdmissionHelpers — the pure validation rules the admit node applies against the collection contract:
# format allow-list (by extension), size cap, and the metadata checks (required user fields
# present, unknown fields per policy, value type per FieldType via the FieldTypeRegistry, enum
# membership). Pure functions — they return precise error strings; the node decides to fail.

# ====== Standard Library Imports ======
from pathlib import PurePosixPath
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.field_types import FieldTypeRegistry
from shared_libs.public_models import (
    FieldOrigin,
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
        # 1. Type check — one handler per FieldType owns its shape rule (bool excluded from numbers…).
        type_error = FieldTypeRegistry.get(spec.field_type).value_error(spec.field_name, value)
        if type_error is not None:
            return type_error

        # 2. Enum membership (a string value, or every item of a keyword list).
        if spec.enum_values is not None:
            items = value if isinstance(value, list) else [value]
            for item in items:
                if item not in spec.enum_values:
                    return (
                        f"field '{spec.field_name}' value {item!r} is not one of {spec.enum_values}"
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
            if (
                spec.origin == FieldOrigin.USER
                and spec.required
                and spec.field_name not in declared
            ):
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
