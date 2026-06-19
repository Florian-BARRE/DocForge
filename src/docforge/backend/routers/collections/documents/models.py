# ====== Code Summary ======
# Request/response models for the Documents section (ingest / list / get / update / reingest / delete).

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, field_validator

# ====== Internal Project Imports ======
from libs.domain.ir.models import ChainTrace


class IngestResponse(BaseModel):
    """Returned immediately after a document is admitted for ingestion."""

    doc_id: uuid.UUID
    status: str
    duplicate: bool
    job_id: uuid.UUID | None = None


class DocumentResponse(BaseModel):
    """A document record with aggregated pipeline state."""

    id: uuid.UUID
    collection_id: uuid.UUID
    source_hash: str
    filename: str
    format: str
    language: str | None
    page_count: int | None
    file_size: int
    status: str
    pipeline_version: str
    user_meta: dict[str, Any]
    implicit_meta: dict[str, Any]
    created_at: datetime

    # Aggregated fields — populated by GET /{document_id}, None on list responses
    chunk_count: int | None = None
    block_count: int | None = None
    has_original: bool = True
    has_pdf: bool = False
    has_markdown: bool = False
    indexed: bool = False
    pipeline_errors: list[str] = Field(default_factory=list)
    # Chain lineage — extracted from implicit_meta by the router so the frontend
    # can render the per-stage attempt log without parsing the meta blob.
    quality_score: float | None = Field(
        default=None,
        description="Parser's intrinsic quality score (blocks_with_text / total).",
    )
    chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description="Document-level chain traces (parse stage).  One entry per stage that ran.",
    )
    embed_chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description="S6 embed chain traces — one entry per batch sent to the embed provider.",
    )

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        """Map DB-internal status values to the API contract expected by clients."""
        return {"processing": "running", "failed": "error"}.get(str(v), str(v))


class DocumentListResponse(BaseModel):
    """Response for GET /documents/list."""

    documents: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class MetadataUpdateRequest(BaseModel):
    """
    Body for metadata update — a partial metadata patch + optional reindex flag.

    The patch is MERGED onto the document's existing user metadata: a provided key overrides
    its current value, a key set to ``null`` removes it, untouched keys are kept.
    """

    metadata: dict[str, Any] = Field(default_factory=dict, description="Partial metadata patch.")
    reindex: bool = Field(default=False, description="Also sync the change into the live index.")


class MetadataUpdateResponse(BaseModel):
    """Result of a metadata update."""

    id: uuid.UUID
    user_meta: dict[str, Any]
    changed_fields: list[str]
    reindexed: bool
    index_sync: dict[str, Any] | None = Field(
        default=None, description="What was synced into Qdrant (when reindex ran)."
    )
    warning: str | None = Field(default=None, description="Why a requested reindex was skipped.")


class ReingestRequest(BaseModel):
    """Body for POST /{document_id}/reingest."""

    force: bool = Field(
        default=False,
        description="Bypass the Merkle node cache and re-run all stages from scratch.",
    )


class ReingestResponse(BaseModel):
    """Result of a reingest request."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    status: str = Field(default="pending", description="Always 'pending' — job is enqueued async.")


class DocumentDeleteResponse(BaseModel):
    """Result of a document delete (cascade across Postgres / Qdrant / S3)."""

    deleted: bool
    id: uuid.UUID
    qdrant_points_deleted: int
    blob_deleted: bool = Field(..., description="False when the blob is shared by another document.")
