# ====== Code Summary ======
# Request/response models of the collection-alias surface — GET /collection-aliases (list), PUT
# /collection-aliases/{name} (create or atomically re-point: the "switch") and DELETE. A collection alias
# is a stable deployment-level name for one collection (keys may be scoped to `alias:<name>`, every
# collection route accepts it in place of the UUID); unrelated to the Qdrant store aliases.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class CollectionAliasModel(BaseModel):
    """One collection alias and the collection it currently targets."""

    name: str = Field(..., description="The alias name (a slug: lowercase, digits, '-', '_').")
    collection_id: str = Field(..., description="The UUID of the collection it points at.")
    collection_name: str = Field(..., description="The name of the collection it points at.")
    created_at: datetime = Field(..., description="When the alias was created.")
    updated_at: datetime = Field(..., description="When the alias was last (re-)pointed.")


class SetCollectionAliasRequest(BaseModel):
    """The body of PUT /collection-aliases/{name}: the collection the alias must point at."""

    model_config = ConfigDict(extra="forbid")

    collection_id: uuid.UUID = Field(..., description="The UUID of the target collection.")


class SetCollectionAliasResponse(CollectionAliasModel):
    """The alias after a create / re-point, plus where it pointed before."""

    previous_collection_id: str | None = Field(
        default=None,
        description="The collection the alias pointed at before this call (null = it was created; "
        "equal to collection_id = a no-op re-point).",
    )
    created: bool = Field(..., description="True when this call created the alias.")


__all__ = ["CollectionAliasModel", "SetCollectionAliasRequest", "SetCollectionAliasResponse"]
