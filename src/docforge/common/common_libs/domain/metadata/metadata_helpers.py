# ====== Code Summary ======
# MetadataHelpers: static-only helper class wrapping the module-level functions for
# metadata field normalization (schema_field_dicts and _field_attr). These functions
# are used by the retrieval engine and the discovery endpoint.

# ====== Standard Library Imports ======
from collections.abc import Iterable
from typing import Any


class MetadataHelpers:
    """
    Static utility helpers for normalizing metadata field specifications.

    Wraps the module-level functions previously in fields.py so callers
    can reference them as MetadataHelpers.schema_field_dicts(...).
    Module-level function aliases are preserved in __init__.py for backward compat.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def field_attr(field: Any, name: str, default: Any = None) -> Any:
        """
        Read a metadata-field attribute from an ORM row, a Pydantic model, or a plain dict.

        Args:
            field (Any): An ORM row, MetaFieldSpec model, or plain dict.
            name (str): Attribute/key name to read.
            default (Any): Default value when the attribute is missing.

        Returns:
            Any: The attribute value, or default if missing.
        """
        if isinstance(field, dict):
            return field.get(name, default)
        return getattr(field, name, default)

    @staticmethod
    def schema_field_dicts(metadata_fields: Iterable[Any]) -> list[dict[str, Any]]:
        """
        Normalize a collection's metadata fields into the canonical plain-dict schema.

        Single source of truth shared by the retrieval engine (which reads ``field_name`` +
        ``semantic``/``lexical``/``filterable``) and the discovery endpoint (which also needs
        ``field_type``/``enum_values``/``required``/``is_system`` to derive filter/weight choices),
        so the two can never disagree on what a collection's fields are.

        Args:
            metadata_fields (Iterable): ORM rows, MetaFieldSpec models, or dicts.

        Returns:
            list[dict[str, Any]]: One dict per field with the full canonical key set.
        """
        return [
            {
                "field_name": MetadataHelpers.field_attr(f, "field_name"),
                "field_type": MetadataHelpers.field_attr(f, "field_type", "string"),
                "required": bool(MetadataHelpers.field_attr(f, "required", False)),
                "filterable": bool(MetadataHelpers.field_attr(f, "filterable", False)),
                "semantic": bool(MetadataHelpers.field_attr(f, "semantic", False)),
                "lexical": bool(MetadataHelpers.field_attr(f, "lexical", False)),
                "enum_values": MetadataHelpers.field_attr(f, "enum_values"),
                "is_system": bool(MetadataHelpers.field_attr(f, "is_system", False)),
                # Provenance — lets the discovery overlay surface origin="generated" fields as the
                # selectable options for pipeline.metagen.targets[*].field.
                "origin": MetadataHelpers.field_attr(f, "origin", "user") or "user",
            }
            for f in metadata_fields
        ]
