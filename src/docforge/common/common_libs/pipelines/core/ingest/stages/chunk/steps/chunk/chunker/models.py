# ====== Code Summary ======
# Internal data structures and the public result type for the structure-aware chunker.
# _Segment and _Special are private traversal intermediates; S4Result is the public output
# (the chunk step's ``chunk_result``) carrying the chunk list + the deterministic config hash.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import Block

# Strategy label stamped on hierarchical parent (section) chunks.
_PARENT_STRATEGY: str = "section_parent"


@dataclass(slots=True)
class _Segment:
    """A contiguous run of content blocks under a single heading path."""

    path: list[str]          # heading texts from root -> this section
    blocks: list[Block]      # content blocks (no headings) belonging to the section


@dataclass(slots=True)
class _Special:
    """An atomic figure/table emitted as its own chunk at its position in reading order."""

    block: Block             # the FIGURE or TABLE block
    path: list[str]          # active heading breadcrumb at this position
    kind: str                # "figure" or "table"


@dataclass(slots=True)
class S4Result:
    """
    Output of the structure-aware chunking step.

    Attributes:
        chunks (list[Chunk]): Chunks with raw_text + prov.heading_path set; embed_text empty.
        config_hash (str): blake2b of the chunking configuration (chunk-id derivation input).
        n_text_chunks (int): Number of text chunks (packed / split sections, and children).
        n_figure_chunks (int): Number of figure chunks.
        n_table_chunks (int): Number of table chunks.
        n_parent_chunks (int): Number of hierarchical parent (section) chunks.
    """

    chunks: list[Chunk]
    config_hash: str
    n_text_chunks: int
    n_figure_chunks: int
    n_table_chunks: int
    n_parent_chunks: int = 0


__all__ = ["S4Result", "_Segment", "_Special", "_PARENT_STRATEGY"]
