# ====== Code Summary ======
# The embed-stage artefacts. The CHUNK stays the textual element (raw + context + generated
# meta); its VECTORS live apart, LINKED by chunk_id — the worker zips both into Qdrant points.
# ChunkVectors carries the main dense/sparse pair plus one named dense vector per SEMANTIC
# contract field (the multi-vector schema declared at collection creation).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .base import Artifact


class SparseVector(BaseModel):
    """A sparse embedding in Qdrant's native shape (parallel indices / values arrays)."""

    indices: list[int] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


class ChunkVectors(BaseModel):
    """
    Every vector of ONE chunk, linked to it by id.

    Attributes:
        chunk_id (str): The chunk these vectors belong to.
        dense (list[float] | None): The main semantic vector (enriched text).
        sparse (SparseVector | None): The lexical vector, when the provider supports it.
        fields (dict): Named dense vectors of the chunk's SEMANTIC metadata fields
            (field name → vector; absent when the chunk has no value for the field).
    """

    chunk_id: str
    dense: list[float] | None = None
    sparse: SparseVector | None = None
    fields: dict[str, list[float]] = Field(default_factory=dict)


class ChunkEmbeddings(Artifact):
    """
    The embed stage's output — one ChunkVectors per chunk, in chunk order.

    Attributes:
        model (str): The embedding model (provenance — stored with the collection's vectors).
        dimension (int): Dense vector dimension (0 when nothing was embedded).
        items (list[ChunkVectors]): One entry per chunk, chunk_id-linked.
    """

    model: str = ""
    dimension: int = 0
    items: list[ChunkVectors] = Field(default_factory=list)


__all__ = ["SparseVector", "ChunkVectors", "ChunkEmbeddings"]
