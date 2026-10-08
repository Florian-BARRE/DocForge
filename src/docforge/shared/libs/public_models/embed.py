# ====== Code Summary ======
# The embed-stage artefacts. The CHUNK stays the textual element (raw + context + generated
# meta); its VECTORS live apart, LINKED by chunk_id — the worker zips both into Qdrant points.
# ChunkVectors carries the main dense/sparse pair plus one named dense vector per SEMANTIC
# contract field and one named sparse vector per LEXICAL contract field (the multi-vector schema
# declared at collection creation).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

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
        field_sparse (dict): Named sparse vectors of the chunk's LEXICAL metadata fields
            (field name → vector; absent when the chunk has no value for the field, or when the
            provider has no sparse axis).
    """

    chunk_id: str
    dense: list[float] | None = None
    sparse: SparseVector | None = None
    fields: dict[str, list[float]] = Field(default_factory=dict)
    field_sparse: dict[str, SparseVector] = Field(default_factory=dict)


class ChunkEmbeddings(Artifact):
    """
    The embed stage's output — one ChunkVectors per chunk, in chunk order.

    Attributes:
        model (str): The embedding model (provenance — stored with the collection's vectors).
        dimension (int): Dense vector dimension (0 when nothing was embedded).
        items (list[ChunkVectors]): One entry per chunk, chunk_id-linked.
        dense_enabled (bool): Whether the embedder has a dense axis (False = sparse-only — the
            store declares no content_dense vector).
        sparse_enabled (bool): Whether sparse vectors were produced.
        sparse_idf (bool): Whether the sparse vectors are term frequencies the store must score with
            its IDF modifier (a bm25_local sparse provider) — drives the vector schema.
    """

    model: str = ""
    dimension: int = 0
    items: list[ChunkVectors] = Field(default_factory=list)
    dense_enabled: bool = True
    sparse_enabled: bool = True
    sparse_idf: bool = False


class VectorLayout(BaseModel):
    """
    The content vector layout a collection's embedder dictates to the store — derived from the embed
    config (never guessed from the live store).

    Attributes:
        dense (bool): The embedder has a dense provider → ``content_dense`` (+ semantic meta vectors).
        sparse (bool): The embedder has a sparse provider → ``content_bm25`` (+ lexical meta vectors).
        sparse_idf (bool): The sparse provider emits term frequencies, so EVERY sparse vector of the
            collection (content and metadata) is declared with the store's IDF modifier.
    """

    model_config = ConfigDict(frozen=True)

    dense: bool = True
    sparse: bool = True
    sparse_idf: bool = False


__all__ = ["SparseVector", "ChunkVectors", "ChunkEmbeddings", "VectorLayout"]
