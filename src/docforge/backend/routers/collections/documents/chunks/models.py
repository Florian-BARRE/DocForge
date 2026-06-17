# ====== Code Summary ======
# Response model for the Chunks section.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


from pydantic import Field


class ChunkResponse(BaseModel):
    """Full materialization of a chunk: raw_text, embed_text, and provenance."""

    id: str
    document_id: str
    config_hash: str
    block_ids: list[str]
    raw_text: str
    embed_text: str
    token_count: int
    strategy: str
    prov: dict[str, Any]
    parent_id: str | None = None


class ChunkListResponse(BaseModel):
    """A page of a document's chunks."""

    chunks: list[ChunkResponse]
    total: int
    limit: int
    offset: int


class ChunkUpdateRequest(BaseModel):
    """Manual correction of a chunk's text (at least one field required)."""

    raw_text: str | None = Field(default=None, description="New display/citation text.")
    embed_text: str | None = Field(default=None, description="New contextualized embed text.")
    reindex: bool = Field(default=False, description="Re-embed the chunk's content vectors.")


class ChunkUpdateResponse(BaseModel):
    """Result of a chunk update."""

    id: str
    raw_text: str
    embed_text: str
    reindexed: bool
    warning: str | None = None
