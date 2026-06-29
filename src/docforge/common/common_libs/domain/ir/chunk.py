# ====== Code Summary ======
# Chunk dataclass — atomic retrieval unit produced by S4 (structure-aware chunker).
# Maps directly to a row in the Postgres `chunk` table and a point in Qdrant.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Chunk:
    """
    Semantic chunk produced by the S4 structure-aware chunker.

    Each chunk carries two text representations:
    - ``raw_text``: faithful text, displayed to users and cited in responses.
    - ``embed_text``: context-augmented text (title + breadcrumb + body), vectorized by S6.

    The ``embed_text`` slot is initially empty and filled by S5 (contextualization stage).
    """

    id: str                          # UUID string — primary key in `chunk` table and Qdrant
    document_id: str                 # UUID string of the owning document
    config_hash: str                 # blake3 of the S4 chunking configuration
    block_ids: list[str]             # source block IDs from the enriched DocumentIR
    raw_text: str                    # faithful text content (displayed / cited)
    embed_text: str                  # context-augmented text (filled by S5, vectorized by S6)
    token_count: int                 # estimated token count of raw_text
    strategy: str                    # chunk kind/method ("token_budget", "semantic", "figure", "table", "section_parent"…)
    prov: dict = field(default_factory=dict)  # aggregated provenance: {pages, block_count, block_types, heading_path, linked_chunk_ids}
    derived_meta: dict = field(default_factory=dict)  # S5b LLM-generated chunk-scope metadata: {generated_field_name: value}
    parent_id: str | None = None     # hierarchical mode: id of the section parent chunk (None for flat / parent chunks)
