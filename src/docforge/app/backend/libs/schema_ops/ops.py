# ====== Code Summary ======
# The explicit metadata-schema operations of a collection PATCH (``field_ops``) — a discriminated
# union on ``op``: add a full field, update some attributes of one, remove one, or rename one. Unlike
# the legacy full-list ``fields`` (where an omitted field is silently removed and a rename is a
# delete + add that destroys the values), every destructive intent here is spelled out.

# ====== Standard Library Imports ======
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType

# ====== Local Project Imports ======
from .field_spec import FIELD_DESCRIPTION_MAX_LENGTH, FieldSpecModel


class FieldPatch(BaseModel):
    """The attributes an ``update`` op changes — only the keys sent are applied (null clears)."""

    model_config = ConfigDict(extra="forbid")

    field_type: FieldType | None = Field(default=None, description="New value type.")
    required: bool | None = Field(default=None, description="New upload-required flag.")
    filterable: bool | None = Field(default=None, description="New filterable flag.")
    lexical: bool | None = Field(default=None, description="New lexical (BM25 vector) flag.")
    semantic: bool | None = Field(default=None, description="New semantic (dense vector) flag.")
    enum_values: list[str] | None = Field(
        default=None, description="New allowed values (enum fields)."
    )
    origin: FieldOrigin | None = Field(default=None, description="New origin (user/generated).")
    scope: FieldScope | None = Field(default=None, description="New scope (document/chunk).")
    description: str | None = Field(
        default=None,
        max_length=FIELD_DESCRIPTION_MAX_LENGTH,
        description="New description (explicit null clears it).",
    )


class AddFieldOp(BaseModel):
    """Add a new field (its name must not already exist)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add"] = Field(description="Operation tag.")
    field: FieldSpecModel = Field(description="The full definition of the new field.")


class UpdateFieldOp(BaseModel):
    """Change some attributes of an existing field in place (its stored values are kept)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["update"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to update.")
    changes: FieldPatch = Field(description="The attributes to change (only the keys sent apply).")


class RemoveFieldOp(BaseModel):
    """Remove a field — DESTRUCTIVE: its stored document/chunk values are deleted with it."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["remove"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to remove.")


class RenameFieldOp(BaseModel):
    """Rename a field in place — its stored values and a ``title_field`` pointing at it follow."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["rename"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to rename.")
    new_name: str = Field(min_length=1, description="Its new name (must not already exist).")


FieldOp = Annotated[
    AddFieldOp | UpdateFieldOp | RemoveFieldOp | RenameFieldOp,
    Field(discriminator="op"),
]

__all__ = [
    "FieldPatch",
    "AddFieldOp",
    "UpdateFieldOp",
    "RemoveFieldOp",
    "RenameFieldOp",
    "FieldOp",
]
