# ====== Code Summary ======
# Request/response models for the Collections section (list / create / delete).
# Metadata field models live in libs/metadata (shared); config models live in the config router.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from common_libs.domain.metadata import MetaFieldSpec


class CreateCollectionRequest(BaseModel):
    """Body for POST /collections/create — the full collection contract."""

    name: str = Field(..., min_length=1, max_length=255)
    supported_formats: list[str] = Field(default=["pdf", "docx", "doc", "xlsx", "pptx", "ppt", "odt", "rtf"])
    max_file_size_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    locality_policy: Literal["on_premise_only", "external_allowed"] = "external_allowed"
    embedding_model: str = "BAAI/bge-m3"
    unknown_field_policy: Literal["reject", "ignore", "store"] = "reject"
    pipeline: dict[str, Any] = Field(default_factory=dict)
    metadata_schema: list[MetaFieldSpec] = Field(default_factory=list)


class CollectionResponse(BaseModel):
    """A collection resource."""

    id: uuid.UUID
    name: str
    supported_formats: list[str]
    max_file_size_bytes: int
    locality_policy: str
    embedding_model: str
    pipeline_version: str
    created_at: datetime

    # Aggregated per-collection document tallies — merged in by the list route from a single
    # grouped COUNT (no N+1). Default 0 so a collection with no documents (absent from the
    # tally map) and any non-list construction path stay valid.
    document_count: int = Field(
        default=0, description="Total number of documents in the collection."
    )
    processed_count: int = Field(
        default=0,
        description="Documents successfully ingested (status='done') — drives the NavRail status dot.",
    )

    model_config = {"from_attributes": True}


class CollectionListResponse(BaseModel):
    """Response for GET /collections/list."""

    collections: list[CollectionResponse]
    total: int


class DeleteResponse(BaseModel):
    """Generic deletion acknowledgement."""

    deleted: bool
    id: uuid.UUID
