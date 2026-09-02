# ====== Code Summary ======
# DatabaseHelpers — the static conventions the façade encodes exactly once: how a DocForge
# collection maps to its Qdrant collection name, the fail-fast guard on vector-name slugs (two
# fields slugging identically would silently share one named vector and corrupt each other), and
# the FieldType → Qdrant payload-index type mapping for filterable fields.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import PayloadType, VectorNames


class DatabaseHelpers:
    """Static conventions shared by the domain façades."""

    # Types whose values can be rendered to text for embedding (semantic/lexical flags).
    _TEXTUAL_TYPES = {
        FieldType.STRING,
        FieldType.TEXT,
        FieldType.ENUM,
        FieldType.KEYWORD_LIST,
        FieldType.TEXT_LIST,
    }

    # A filterable field's declared type → how Qdrant indexes its payload value.
    PAYLOAD_TYPES: dict[FieldType, PayloadType] = {
        FieldType.STRING: PayloadType.KEYWORD,
        FieldType.KEYWORD_LIST: PayloadType.KEYWORD,
        FieldType.INTEGER: PayloadType.INTEGER,
        FieldType.FLOAT: PayloadType.FLOAT,
        FieldType.BOOL: PayloadType.BOOL,
        FieldType.DATETIME: PayloadType.DATETIME,
        FieldType.ENUM: PayloadType.KEYWORD,
        FieldType.TEXT: PayloadType.TEXT,
        # Qdrant indexes array payloads natively — a filter matches ANY element.
        FieldType.INTEGER_LIST: PayloadType.INTEGER,
        FieldType.FLOAT_LIST: PayloadType.FLOAT,
        # Sentences filter by full-text match, never exact keyword equality.
        FieldType.TEXT_LIST: PayloadType.TEXT,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DatabaseHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def qdrant_collection_name(collection_id: uuid.UUID | str) -> str:
        """
        The Qdrant collection backing a DocForge collection — stable, id-derived.

        Accepts a ``UUID`` or its string form: callers coming straight from a request path or a
        serialized id pass a str, so coerce here rather than let ``.hex`` blow up on a str.

        Args:
            collection_id (uuid.UUID | str): The collection id (either representation).

        Returns:
            str: The deterministic ``col_<hex>`` Qdrant collection name.
        """
        canonical = collection_id if isinstance(collection_id, uuid.UUID) else uuid.UUID(collection_id)
        return f"col_{canonical.hex}"

    @staticmethod
    def validate_vector_slugs(fields: Sequence[MetadataField]) -> None:
        """
        Fail fast when two searchable fields would collide on one Qdrant vector name.

        Slugging strips accents/punctuation ("Café" and "Cafe" both slug to "cafe"), and a named
        vector is created per slug — a collision would make two fields silently share (and corrupt)
        one vector. Runs at collection creation, before anything is spent.

        Args:
            fields (Sequence[MetadataField]): The collection's metadata schema.

        Raises:
            ValueError: On an empty slug or a slug shared by two searchable fields.
        """
        seen: dict[str, str] = {}
        for field in fields:
            # An enum field without its whitelist is an unusable contract — refuse early.
            if field.field_type == FieldType.ENUM and not field.enum_values:
                raise ValueError(
                    f"Field '{field.field_name}' is enum-typed but declares no enum_values."
                )
            if not (field.semantic or field.lexical):
                continue
            # Only textual values can be embedded — a semantic number list is meaningless.
            if field.field_type not in DatabaseHelpers._TEXTUAL_TYPES:
                raise ValueError(
                    f"Field '{field.field_name}' ({field.field_type.value}) cannot be "
                    f"semantic/lexical — only textual types can be embedded."
                )
            slug = VectorNames.slug(field.field_name)
            if not slug:
                raise ValueError(f"Field name '{field.field_name}' slugs to nothing usable.")
            if slug in seen:
                raise ValueError(
                    f"Fields '{seen[slug]}' and '{field.field_name}' collide on vector slug "
                    f"'{slug}' — rename one of them."
                )
            seen[slug] = field.field_name

    @classmethod
    def payload_type_for(cls, field_type: FieldType) -> PayloadType:
        """The Qdrant payload-index type for a filterable field's declared type."""
        return cls.PAYLOAD_TYPES[field_type]


__all__ = ["DatabaseHelpers"]
