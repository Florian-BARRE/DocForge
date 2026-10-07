# ====== Code Summary ======
# Collection metadata-schema operations, mirrored from the DocForge backend: the ``field_ops``
# discriminated union of a collection PATCH (add / update / remove / rename) and the ``SchemaDiff``
# every PATCH response carries (applied, or previewed under ``dry_run``).

# ====== Standard Library Imports ======
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import FieldOrigin, FieldScope, FieldType
from .field_spec import FieldSpec


class FieldPatch(BaseModel):
    """
    The attributes an ``update`` op changes — only the keys set are sent (null clears).

    Attributes:
        field_type / required / filterable / lexical / semantic / enum_values / origin / scope /
            description: The new value of each attribute to change.
    """

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
        default=None, max_length=1000, description="New description (explicit null clears it)."
    )


class AddFieldOp(BaseModel):
    """Add a new field (its name must not already exist)."""

    op: Literal["add"] = Field(description="Operation tag.")
    field: FieldSpec = Field(description="The full definition of the new field.")


class UpdateFieldOp(BaseModel):
    """Change some attributes of an existing field in place (its stored values are kept)."""

    op: Literal["update"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to update.")
    changes: FieldPatch = Field(description="The attributes to change (only the keys set apply).")


class RemoveFieldOp(BaseModel):
    """Remove a field — DESTRUCTIVE: its stored document/chunk values are deleted with it."""

    op: Literal["remove"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to remove.")


class RenameFieldOp(BaseModel):
    """Rename a field in place — its stored values and a ``title_field`` pointing at it follow."""

    op: Literal["rename"] = Field(description="Operation tag.")
    field_name: str = Field(description="The existing field to rename.")
    new_name: str = Field(min_length=1, description="Its new name (must not already exist).")


FieldOp = Annotated[
    AddFieldOp | UpdateFieldOp | RemoveFieldOp | RenameFieldOp,
    Field(discriminator="op"),
]


class SchemaDiffModifiedField(BaseModel):
    """One field updated in place, with the attributes that changed."""

    field_name: str = Field(description="The field's (post-PATCH) name.")
    changed_attrs: list[str] = Field(description="The attributes whose value changed.")


class SchemaDiffRename(BaseModel):
    """One field renamed in place (its values are kept)."""

    from_name: str = Field(description="The field's previous name.")
    to_name: str = Field(description="The field's new name.")


class SchemaDiff(BaseModel):
    """
    The metadata-schema change of a collection PATCH (applied, or previewed under dry_run).

    Attributes:
        added (list[str]): Fields created.
        modified (list[SchemaDiffModifiedField]): Fields updated in place (values kept).
        removed (list[str]): Fields deleted with their stored values.
        renamed (list[SchemaDiffRename]): Fields renamed in place (values kept).
        values_lost (dict[str, int]): Removed field → stored document + chunk values deleted.
        reindex_required_fields (list[str]): Fields needing a reindex before being searchable.
    """

    added: list[str] = Field(default_factory=list, description="Fields created.")
    modified: list[SchemaDiffModifiedField] = Field(
        default_factory=list, description="Fields updated in place (values kept)."
    )
    removed: list[str] = Field(
        default_factory=list, description="Fields deleted with their stored values."
    )
    renamed: list[SchemaDiffRename] = Field(
        default_factory=list, description="Fields renamed in place (values kept)."
    )
    values_lost: dict[str, int] = Field(
        default_factory=dict, description="Removed field → stored values deleted with it."
    )
    reindex_required_fields: list[str] = Field(
        default_factory=list, description="Fields whose change needs a reindex to be searchable."
    )


__all__ = [
    "FieldPatch",
    "AddFieldOp",
    "UpdateFieldOp",
    "RemoveFieldOp",
    "RenameFieldOp",
    "FieldOp",
    "SchemaDiff",
    "SchemaDiffModifiedField",
    "SchemaDiffRename",
]
