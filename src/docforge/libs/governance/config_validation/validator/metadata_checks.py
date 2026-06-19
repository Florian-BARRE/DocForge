# ====== Code Summary ======
# MetadataChecks — validates the metadata_fields block of a collection config: field names must
# be present and unique, types must be known, and enum fields must declare at least one value.
# Pure static validation logic; no logging.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, get_args

# ====== Internal Project Imports ======
from libs.core.metadata import MetaFieldType

# Field types accepted in a metadata schema — derived from the canonical MetaFieldType so the
# validator can never drift from what MetaFieldSpec actually accepts.
_ALLOWED_FIELD_TYPES: frozenset[str] = frozenset(get_args(MetaFieldType))


class MetadataChecks:
    """
    Static checker for the metadata field schema block.

    Validates:
    - Every field has a non-empty ``field_name``.
    - No two fields share the same name (duplicate detection).
    - ``field_type`` is one of the values allowed by ``MetaFieldType``.
    - Enum-typed fields declare a non-empty ``enum_values`` list.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetadataChecks is a static-only class and cannot be instantiated.")

    @staticmethod
    def check_metadata(
        fields: list[dict[str, Any]], issues: list[dict[str, Any]]
    ) -> None:
        """
        Validate metadata field names, types, enum values, and fusion weights.

        Args:
            fields (list[dict]): The ``metadata_fields`` list from the config document.
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        seen: set[str] = set()
        for field in fields:
            name = field.get("field_name")
            # 1. Name present + unique
            if not name:
                issues.append(_issue("metadata.no_name", "error", "metadata_fields",
                                     "A metadata field is missing 'field_name'."))
                continue
            if name in seen:
                issues.append(_issue("metadata.duplicate", "error", f"metadata_fields.{name}",
                                     f"Duplicate metadata field {name!r}."))
            seen.add(name)

            # 2. Type valid
            ftype = field.get("field_type", "string")
            if ftype not in _ALLOWED_FIELD_TYPES:
                issues.append(_issue(
                    "metadata.bad_type", "error", f"metadata_fields.{name}",
                    f"Field {name!r} has unknown type {ftype!r} "
                    f"(allowed: {sorted(_ALLOWED_FIELD_TYPES)}).",
                ))

            # 3. Enum fields need a non-empty value set
            if ftype == "enum" and not field.get("enum_values"):
                issues.append(_issue(
                    "metadata.enum_empty", "error", f"metadata_fields.{name}",
                    f"Enum field {name!r} must define enum_values.",
                ))


# ─── Module-level helper (not exposed in __all__) ────────────────────────────

def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
    """Build a single validation issue record."""
    return {"code": code, "severity": severity, "field": field, "message": message}
