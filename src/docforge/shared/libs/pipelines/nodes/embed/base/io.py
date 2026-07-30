# ====== Code Summary ======
# The fixed I/O contract shared by EVERY embedder: the chunks (their ENRICHED text is what gets
# embedded) + the contract (the semantic fields to vectorise) in, the chunk-linked vectors out.
# The chunk stays the textual element; its vectors live apart, linked by chunk_id.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import Chunk, ChunkEmbeddings, CollectionContract


class EmbedConsumes(NodeInput):
    """Input of any embedder — the final chunks + the contract (semantic fields)."""

    chunks: list[Chunk] = Field(
        default_factory=list,
        description="The final chunks — their ENRICHED text is what gets embedded.",
    )
    contract: CollectionContract = Field(
        description="The contract (its semantic chunk fields get per-field vectors)."
    )


class EmbedProduces(NodeOutput):
    """Output of any embedder — every chunk's vectors, chunk_id-linked."""

    embeddings: ChunkEmbeddings = Field(
        description="Every chunk's vectors, linked by chunk_id, in chunk order."
    )


__all__ = ["EmbedConsumes", "EmbedProduces"]
