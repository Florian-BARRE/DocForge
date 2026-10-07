# ====== Code Summary ======
# FieldSpecModel — one metadata field of a collection's contract, the shape every schema surface
# shares (create, the legacy full-list PATCH, the ``add`` field op, snippets). Lives in the schema_ops
# lib (not the router) so the op planner can build on it without importing a router module.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType

# Upper bound of a metadata field's free-text description (a sentence or two, not a document).
FIELD_DESCRIPTION_MAX_LENGTH = 1000


class FieldSpecModel(BaseModel):
    """One metadata field of the collection's contract (declared OR generated)."""

    # A typo in a field flag (filterable/lexical/semantic) must FAIL, never be silently dropped —
    # a swallowed flag would build the wrong vector space. Mirrors the pipeline's extra="forbid".
    model_config = ConfigDict(extra="forbid")

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
        max_length=FIELD_DESCRIPTION_MAX_LENGTH,
        description=(
            "What the field means, for humans and agents (e.g. 'Business process the document "
            "belongs to'). Documentation only: editing it never triggers a reindex. null = none."
        ),
    )


__all__ = ["FieldSpecModel", "FIELD_DESCRIPTION_MAX_LENGTH"]
