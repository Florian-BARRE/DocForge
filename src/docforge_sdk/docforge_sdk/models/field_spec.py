# ====== Code Summary ======
# FieldSpec — one metadata field of a collection's contract, mirrored from the backend
# ``FieldSpecModel``. Its own module so both the collections and the schema-ops models build on it.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import FieldOrigin, FieldScope, FieldType


class FieldSpec(BaseModel):
    """
    One metadata field of the collection's contract (declared OR generated).

    Attributes:
        field_name (str): Unique field name within the collection.
        field_type (FieldType): Value type — drives validation and storage.
        required (bool): Upload refused without it (user fields).
        filterable (bool): Present in the Qdrant payload (lean vector).
        lexical (bool): Gets a sparse BM25 named vector.
        semantic (bool): Gets a dense named vector.
        enum_values (list[str] | None): Allowed values when ``field_type`` is enum.
        origin (FieldOrigin): user (declared at upload) or generated (metagen).
        scope (FieldScope): document or chunk level value.
        description (str | None): What the field means (max 1000 chars).
    """

    field_name: str = Field(description="Unique field name within the collection.")
    field_type: FieldType = Field(description="Value type — drives validation and storage.")
    required: bool = Field(default=False, description="Upload refused without it (user fields).")
    filterable: bool = Field(default=False, description="Present in the Qdrant payload (lean).")
    lexical: bool = Field(default=False, description="Gets a sparse BM25 named vector.")
    semantic: bool = Field(default=False, description="Gets a dense named vector.")
    enum_values: list[str] | None = Field(
        default=None, description="Allowed values when field_type is enum."
    )
    origin: FieldOrigin = Field(
        default=FieldOrigin.USER, description="user (declared at upload) or generated (metagen)."
    )
    scope: FieldScope = Field(
        default=FieldScope.DOCUMENT, description="document or chunk level value."
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="What the field means, in plain words — surfaced to search clients (max 1000).",
    )


__all__ = ["FieldSpec"]
