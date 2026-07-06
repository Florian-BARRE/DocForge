# ====== Code Summary ======
# Pydantic models for the collections router — the contract the UI creates and edits:
# identity + limits, the FULL metadata schema (declared up front: named vectors cannot be
# added to Qdrant later), and the two config blobs (pipeline graph + search).

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType


class FieldSpecModel(BaseModel):
    """One metadata field of the collection's contract (declared OR generated)."""

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


class CollectionModel(BaseModel):
    """One collection — the full contract the UI displays and edits."""

    id: str = Field(description="The collection's UUID.")
    name: str = Field(description="Unique human name.")
    supported_formats: list[str] = Field(description="Accepted upload extensions (e.g. pdf).")
    max_file_size_bytes: int = Field(description="Upload size ceiling, bytes.")
    needs_reindex: bool = Field(description="True when a config change requires reindexing.")
    created_at: datetime | None = Field(default=None, description="Creation timestamp.")
    pipeline: dict[str, Any] = Field(description="The ingestion pipeline blob (the graph).")
    search: dict[str, Any] = Field(description="The search config blob.")
    fields: list[FieldSpecModel] = Field(default_factory=list, description="The metadata schema.")


class CreateCollectionRequest(BaseModel):
    """Create a collection from A to Z — contract, schema and (optionally) its pipeline."""

    name: str = Field(description="Unique human name.")
    supported_formats: list[str] = Field(description="Accepted upload extensions (e.g. pdf).")
    max_file_size_bytes: int = Field(description="Upload size ceiling, bytes.")
    fields: list[FieldSpecModel] = Field(
        default_factory=list,
        description="The FULL schema, declared up front (vector space is fixed at creation).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None,
        description="The pipeline blob; omitted → the product default (all stages wired).",
    )


class UpdateCollectionRequest(BaseModel):
    """
    Patch any part of the collection — identity/limits, metadata schema, config blobs.

    Schema updates are applied by DIFF (existing values survive untouched fields); a change
    to the SEARCHABLE surface flips needs_reindex. Config changes append immutable versions.
    """

    name: str | None = Field(default=None, description="New unique name.")
    supported_formats: list[str] | None = Field(
        default=None, description="New accepted upload extensions."
    )
    max_file_size_bytes: int | None = Field(default=None, description="New size ceiling, bytes.")
    fields: list[FieldSpecModel] | None = Field(
        default=None,
        description="The TARGET schema (diffed by field name; omitted fields are removed).",
    )
    pipeline: dict[str, Any] | None = Field(
        default=None, description="New pipeline blob (validated before being stored)."
    )
    search: dict[str, Any] | None = Field(default=None, description="New search config blob.")
    note: str | None = Field(default=None, description="Version note shown in the history.")


__all__ = [
    "FieldSpecModel",
    "CollectionModel",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
]
