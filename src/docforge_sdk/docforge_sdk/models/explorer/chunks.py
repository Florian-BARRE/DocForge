# ====== Code Summary ======
# Explorer chunk models: a chunk with its composition, a page of chunks and a chunk's context.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .documents import MetadataValue


class ChunkInfo(BaseModel):
    """
    One retrieval chunk — enriched text, composition (block ids) and generated metadata.

    Attributes:
        id (str): The chunk UUID (doubles as the Qdrant point id).
        chunk_index (int): Position of the chunk within the document.
        text (str): The enriched, embedded text.
        token_count (int): Token length of the enriched text.
        is_indexed (bool): Whether the chunk is upserted into Qdrant.
        role (str): Structural classification set by the pipeline.
        enabled (bool): Effective searchability (override when set, else the role default).
        strategy (str): The chunking strategy that produced it.
        parent_id (str | None): Parent chunk (hierarchical chunking).
        block_ids (list[str]): Composing IR block ids, in assembly order.
        metadata (list[MetadataValue]): Per-chunk generated metadata values.
        heading_path (list[str]): The chunk's section breadcrumb (outer→inner headings).
        page (int | None): Page of the chunk's primary block (0-based); None when unlocated.
        page_number (int | None): The same page, 1-based (as a reader counts it); None when unlocated.
    """

    id: str = Field(description="The chunk UUID (doubles as the Qdrant point id).")
    chunk_index: int = Field(description="Position of the chunk within the document.")
    text: str = Field(description="The enriched, embedded text.")
    token_count: int = Field(description="Token length of the enriched text.")
    is_indexed: bool = Field(description="Whether the chunk is upserted into Qdrant.")
    role: str = Field(description="Structural classification set by the pipeline.")
    enabled: bool = Field(description="Effective searchability (override or role default).")
    strategy: str = Field(description="The chunking strategy that produced it.")
    parent_id: str | None = Field(default=None, description="Parent chunk (hierarchical chunking).")
    block_ids: list[str] = Field(
        default_factory=list, description="Composing IR block ids, in assembly (position) order."
    )
    metadata: list[MetadataValue] = Field(
        default_factory=list, description="Per-chunk generated metadata values."
    )
    heading_path: list[str] = Field(
        default_factory=list,
        description="The chunk's section breadcrumb (outer→inner headings); [] when none.",
    )
    page: int | None = Field(
        default=None,
        description="Page of the chunk's primary block (0-based); None when it has no located block.",
    )
    page_number: int | None = Field(
        default=None,
        description="The same page, 1-based (as a reader counts it); None when unlocated.",
    )


class ChunkPage(BaseModel):
    """
    One page of a document's chunks together with the document's total chunk count.

    SDK-only wrapper (not an OpenAPI schema): the REST body is a bare chunk array and the total
    travels in the ``X-Total-Count`` response header.

    Attributes:
        items (list[ChunkInfo]): The chunks of this page, in chunk_index order.
        total (int | None): The document's total chunk count; None against a server that predates
            the header.
    """

    items: list[ChunkInfo] = Field(description="The chunks of this page, in chunk_index order.")
    total: int | None = Field(
        default=None, description="The document's total chunk count (X-Total-Count header)."
    )


class ContextChunk(BaseModel):
    """
    One chunk of a context window (lean projection of a chunk).

    Attributes:
        chunk_id (str): The chunk UUID.
        chunk_index (int): Position of the chunk within its document.
        text (str): The chunk's (enriched) text.
        page_number (int | None): 1-based page of the chunk's leading block; None when unlocated.
        heading_path (list[str]): The chunk's section breadcrumb (outer to inner).
        token_count (int): Token length of the text.
        is_target (bool): True for the chunk the window was requested around.
    """

    chunk_id: str = Field(description="The chunk UUID.")
    chunk_index: int = Field(description="Position of the chunk within its document.")
    text: str = Field(description="The chunk's (enriched) text.")
    page_number: int | None = Field(default=None, description="1-based page; null when unlocated.")
    heading_path: list[str] = Field(
        default_factory=list, description="The chunk's section breadcrumb (outer to inner)."
    )
    token_count: int = Field(description="Token length of the text.")
    is_target: bool = Field(description="True for the chunk the window was requested around.")


class ChunkContext(BaseModel):
    """
    A chunk and its neighbours within the same document (a reading window around a search hit).

    Attributes:
        document_id (str): The owning document's UUID.
        display_title (str): The owning document's display title.
        chunks (list[ContextChunk]): The window in chunk_index order, the target flagged.
    """

    document_id: str = Field(description="The owning document's UUID.")
    display_title: str = Field(description="The owning document's display title.")
    chunks: list[ContextChunk] = Field(
        description="The window in chunk_index order, the target flagged is_target."
    )
