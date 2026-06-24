# ====== Code Summary ======
# DocumentIR model: canonical Intermediate Representation of a parsed document.
# All downstream stages (enrichment, serialization, chunking, embedding) consume
# the DocumentIR — it is the pivot of the entire DocForge system.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .block import Block
from .chain_trace import ChainTrace
from .enums import BlockType


class DocumentIR(BaseModel):
    """
    Canonical Intermediate Representation of a parsed document.

    This is the pivot of the system.  All downstream stages (enrichment, serialization,
    chunking, embedding) consume the DocumentIR, never the raw source or the flat markdown.
    """

    doc_id: str = Field(..., description="Unique document identifier (UUID).")
    title: str = Field(
        default="",
        description="Document title extracted by the parser (empty when unavailable).",
    )
    source_hash: str = Field(
        ...,
        description="SHA-256 hex digest of the original file bytes; used for content-addressing.",
    )
    pipeline_fingerprints: dict[str, str] = Field(
        default_factory=dict,
        description="Stage name → blake3 fingerprint; tracks which config produced each artifact.",
    )
    n_pages: int = Field(..., description="Total page count.")
    language: str = Field(
        ...,
        description="Dominant ISO 639-1 language code of the document.",
    )
    blocks: list[Block] = Field(
        default_factory=list,
        description="All blocks in reading order; heading tree encoded via parent_id.",
    )
    quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Parser-reported quality estimate for THIS IR (e.g. textual blocks / total). "
            "Used by the S1 parse chain's gate to decide escalation."
        ),
    )
    chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description=(
            "Document-level provider chain attempts (parse, embed).  Empty by "
            "default so legacy IR rows still load."
        ),
    )

    @property
    def heading_blocks(self) -> list[Block]:
        """Return only HEADING blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.HEADING]

    @property
    def figure_blocks(self) -> list[Block]:
        """Return only FIGURE blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.FIGURE]

    @property
    def table_blocks(self) -> list[Block]:
        """Return only TABLE blocks, in reading order."""
        return [b for b in self.blocks if b.type == BlockType.TABLE]
