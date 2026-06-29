# ====== Code Summary ======
# ConfigFieldNormalizer — stateless helper that coerces a metadata field from any
# supported source (ORM row, Pydantic model, or dict) into the canonical persisted
# key set. Extracted from ConfigDocument so the document builder stays focused on
# construction and merging.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.metadata import MetaFieldSpec


class ConfigFieldNormalizer:
    """
    Static helper that normalizes a metadata field to the canonical key set.

    Accepts a MetadataFieldModel (ORM), a MetaFieldSpec (Pydantic), or a plain dict
    and projects it onto exactly the persisted metadata-field keys, filling defaults.
    """

    logger = loggerplusplus.bind(identifier="ConfigFieldNormalizer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ConfigFieldNormalizer is a static-only class and cannot be instantiated.")

    @staticmethod
    def to_dict(field: Any) -> dict[str, Any]:
        """
        Normalize a metadata field (ORM row, Pydantic model, or dict) to the canonical keys.

        Args:
            field (Any): A MetadataFieldModel, MetaFieldSpec, or plain dict.

        Returns:
            dict: A dict with exactly the persisted metadata-field keys, defaults filled.
        """
        # 1. Coerce any supported source into a plain dict
        if hasattr(field, "model_dump"):
            src = field.model_dump()
        elif isinstance(field, dict):
            src = field
        else:
            src = {k: getattr(field, k, None) for k in MetaFieldSpec.model_fields}

        # 2. Project onto the canonical key set with sensible defaults
        return {
            "field_name": src["field_name"],
            "field_type": src.get("field_type", "string"),
            "required": bool(src.get("required", False)),
            "filterable": bool(src.get("filterable", False)),
            "lexical": bool(src.get("lexical", False)),
            "semantic": bool(src.get("semantic", False)),
            "enum_values": src.get("enum_values"),
            "is_system": bool(src.get("is_system", False)),
            # Provenance discriminator: 'system' (pipeline-extracted), 'user' (uploaded values),
            # 'generated' (produced by S5b). Carried end-to-end so generated fields round-trip.
            "origin": src.get("origin", "user") or "user",
        }
