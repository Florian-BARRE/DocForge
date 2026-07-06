# ====== Code Summary ======
# The chunk artefact — the RAW retrieval unit the chunk stage produces from the enriched IR.
# Raw means pre-contextualisation: the next stage enriches the TEXT (breadcrumb prefix, LLM
# context) without touching the structural identity carried here. block_ids is THE chunk ↔ IR
# relation (the chunk_block table); heading_path is computed at chunking time (the tree is at
# hand) and rendered later by contextualize.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact


class Chunk(Artifact):
    """
    One raw retrieval unit — a contiguous span of IR blocks assembled into text.

    Attributes:
        chunk_id (str): Stable identifier within the document (doc_id + ordinal).
        ordinal (int): Reading-order position among the document's chunks (0-indexed).
        text (str): The RAW assembled text — never touched after chunking.
        block_ids (list[str]): The IR blocks this chunk is made of, in reading order.
        token_count (int): Token count of ``text`` (the chunker's tokenizer).
        heading_path (list[str]): Section ancestry, top-down (e.g. ["Chapter 2", "Results"]).
        page_start (int): First source page covered (0-indexed).
        page_end (int): Last source page covered (0-indexed).
        context (str): Retrieval context ACCUMULATED by the contextualize stage (each method
            appends its piece); empty until then. The raw text stays intact — the enriched
            view is re-derivable.
        generated_meta (dict): CHUNK-scope generated metadata filled by the metagen stage
            (field name → coerced value, per the collection contract); empty until then.
    """

    chunk_id: str
    ordinal: int
    text: str
    block_ids: list[str] = Field(default_factory=list)
    token_count: int = 0
    heading_path: list[str] = Field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    context: str = ""
    generated_meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def enriched_text(self) -> str:
        """The text to embed/search — the accumulated context above the raw text."""
        return f"{self.context}\n\n{self.text}" if self.context else self.text


__all__ = ["Chunk"]
