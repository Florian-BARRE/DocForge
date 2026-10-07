# ====== Code Summary ======
# SchemaDiff — what a collection PATCH did (or, under dry_run, would do) to the metadata schema:
# the added / modified / removed / renamed fields, the stored values each removal destroys, and the
# fields whose change needs a reindex before they are searchable. Always present on the PATCH
# response (empty when the PATCH did not touch the schema).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class SchemaDiffModifiedField(BaseModel):
    """One field updated in place, with the attributes that changed."""

    field_name: str = Field(description="The field's (post-PATCH) name.")
    changed_attrs: list[str] = Field(
        description="The attributes whose value changed (e.g. 'filterable', 'description')."
    )


class SchemaDiffRename(BaseModel):
    """One field renamed in place (its values are kept)."""

    from_name: str = Field(description="The field's previous name.")
    to_name: str = Field(description="The field's new name.")


class SchemaDiff(BaseModel):
    """The metadata-schema change of a collection PATCH (applied, or previewed under dry_run)."""

    added: list[str] = Field(default_factory=list, description="Fields created.")
    modified: list[SchemaDiffModifiedField] = Field(
        default_factory=list, description="Fields updated in place (values kept)."
    )
    removed: list[str] = Field(
        default_factory=list,
        description="Fields deleted — their stored values are deleted with them (see values_lost).",
    )
    renamed: list[SchemaDiffRename] = Field(
        default_factory=list, description="Fields renamed in place (values kept)."
    )
    values_lost: dict[str, int] = Field(
        default_factory=dict,
        description="Removed field → number of stored document + chunk values deleted with it.",
    )
    reindex_required_fields: list[str] = Field(
        default_factory=list,
        description="Fields whose change needs a reindex before they are searchable (a new or "
        "renamed semantic/lexical field, a newly semantic/lexical one, or a searchable field whose "
        "type changed). Empty for a never-indexed collection.",
    )


__all__ = ["SchemaDiff", "SchemaDiffModifiedField", "SchemaDiffRename"]
