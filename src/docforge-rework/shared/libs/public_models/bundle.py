# ====== Code Summary ======
# The RunBundle — the ingestion pipeline's OUTPUT CONTRACT: everything a run produced, in one
# typed artefact. The graph stays pure (nodes know no storage); the worker consumes exactly ONE
# artefact and persists it (S3 → Postgres → Qdrant). A pipeline whose final node does not
# produce a RunBundle is not a valid ingestion pipeline — the runner refuses it loudly.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact
from .chunk import Chunk
from .embed import ChunkEmbeddings
from .intake import IntakeResult
from .ir import DocumentIR
from .metagen import GeneratedDocumentMeta
from .render import PageRenders


class RunBundle(Artifact):
    """
    Everything one ingestion run produced — what the worker persists.

    Attributes:
        ingest (IntakeResult): The intake facts (source hash, working PDF, page count).
        ir (DocumentIR): The ENRICHED canonical document (figure slots filled).
        pages (PageRenders | None): The full-page renders — None when the pipeline has no
            render stage (no page images stored, nothing else changes).
        chunks (list[Chunk]): The final retrieval units (context + generated_meta aboard).
        document_meta (GeneratedDocumentMeta | None): The document-scope generated values —
            None when the pipeline has no metagen stage.
        embeddings (ChunkEmbeddings | None): Every chunk's vectors — None when the pipeline
            has no embed stage (nothing lands in Qdrant; Postgres truth is complete).
    """

    ingest: IntakeResult
    ir: DocumentIR
    pages: PageRenders | None = None
    chunks: list[Chunk] = Field(default_factory=list)
    document_meta: GeneratedDocumentMeta | None = None
    embeddings: ChunkEmbeddings | None = None


__all__ = ["RunBundle"]
