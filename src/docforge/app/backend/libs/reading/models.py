# ====== Code Summary ======
# The response contract of the document-READING surface — what an agent needs to read a document
# piecemeal: the heading outline (where each section starts, which chunk opens it) and the context
# window around one chunk (its neighbours by chunk_index, lean — no geometry, no metadata).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class OutlineHeading(BaseModel):
    """One heading of a document's outline, in reading order."""

    level: int = Field(description="Heading depth (1 = top level; 1 when the parser set none).")
    text: str = Field(description="The heading text.")
    page_number: int | None = Field(
        default=None,
        description="1-based page the heading sits on; null for a page-less document (e.g. HTML).",
    )
    chunk_id: str | None = Field(
        default=None,
        description="The first chunk of this section (whose heading_path ends with — else contains — "
        "this heading); read around it with GET /chunks/{chunk_id}/context. Null when no chunk "
        "carries this heading in its breadcrumb.",
    )


class DocumentOutline(BaseModel):
    """A document's heading outline — its table of contents, built from the IR heading blocks."""

    document_id: str = Field(description="The document's UUID.")
    display_title: str = Field(
        description="The title to show: the collection's title_field value when set, else the "
        "parsed title ('' when none)."
    )
    page_count: int | None = Field(
        default=None, description="Pages of the document (null before parse / page-less formats)."
    )
    headings: list[OutlineHeading] = Field(
        default_factory=list, description="Every heading, in reading order ([] when none)."
    )


class ContextChunk(BaseModel):
    """One chunk of a context window — lean: text and citation facts, no geometry or metadata."""

    chunk_id: str = Field(description="The chunk UUID.")
    chunk_index: int = Field(description="Position of the chunk within its document.")
    text: str = Field(description="The chunk's (enriched) text.")
    page_number: int | None = Field(
        default=None,
        description="1-based page of the chunk's leading block; null when it has no located block.",
    )
    heading_path: list[str] = Field(
        default_factory=list, description="The chunk's section breadcrumb (outer→inner)."
    )
    token_count: int = Field(description="Token length of the text.")
    is_target: bool = Field(description="True for the chunk the window was requested around.")


class ChunkContext(BaseModel):
    """A chunk and its enabled neighbours by chunk_index within the same document."""

    document_id: str = Field(description="The owning document's UUID.")
    display_title: str = Field(description="The owning document's display title.")
    chunks: list[ContextChunk] = Field(
        description="The window in chunk_index order: up to 'before' preceding chunks, the target "
        "(is_target=true) and up to 'after' following chunks. Disabled neighbours are skipped (the "
        "window reaches past them); fewer are returned at a document edge."
    )


__all__ = ["OutlineHeading", "DocumentOutline", "ContextChunk", "ChunkContext"]
