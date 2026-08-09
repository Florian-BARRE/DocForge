# ====== Code Summary ======
# Response models for the collection storage-footprint endpoint, mirrored field-for-field from the
# DocForge backend router models (S3FootprintModel / PostgresFootprintModel / QdrantFootprintModel /
# DocumentStorageModel / CollectionStorageResponse). S3 bytes are EXACT; Postgres and Qdrant bytes are
# ESTIMATES — each section carries its own ``estimated`` flag.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class S3FootprintModel(BaseModel):
    """
    EXACT S3 bytes from the content-addressed blob registry (``estimated`` is always false).

    Attributes:
        original_bytes (int): Uploaded source file bytes.
        rendered_bytes (int): Derived-blob bytes (canonical PDF, page renders, crops).
        total_bytes (int): Logical bytes (original + rendered).
        physical_unique_bytes (int): Deduped disk cost — a blob shared across documents counts
            once (<= total).
        estimated (bool): Always false: S3 bytes are measured exactly.
    """

    original_bytes: int = Field(description="Uploaded source file bytes.")
    rendered_bytes: int = Field(
        description="Derived-blob bytes (canonical PDF, page renders, crops)."
    )
    total_bytes: int = Field(description="Logical bytes (original + rendered).")
    physical_unique_bytes: int = Field(
        description="Deduped disk cost — a blob shared across documents counts once (<= total)."
    )
    estimated: bool = Field(description="Always false: S3 bytes are measured exactly.")


class PostgresFootprintModel(BaseModel):
    """
    ESTIMATED Postgres row bytes via ``pg_column_size`` (excludes index/TOAST/bloat).

    Attributes:
        documents_bytes (int): ``document`` + ``page`` rows.
        ir_blocks_bytes (int): ``block`` + ``block_table`` + ``block_figure`` rows.
        enrichment_bytes (int): ``block_enrichment`` + ``enrichment_attempt`` rows.
        chunks_bytes (int): ``chunk`` + ``chunk_block`` + ``chunk_metadata`` + ``entity_mention`` rows.
        metadata_bytes (int): ``document_metadata`` rows.
        observability_bytes (int): ``job`` + ``job_stage_event`` rows.
        total_bytes (int): Sum of every bucket.
        estimated (bool): Always true: real row bytes, no index/TOAST/bloat.
    """

    documents_bytes: int = Field(description="``document`` + ``page`` rows.")
    ir_blocks_bytes: int = Field(description="``block`` + ``block_table`` + ``block_figure`` rows.")
    enrichment_bytes: int = Field(description="``block_enrichment`` + ``enrichment_attempt`` rows.")
    chunks_bytes: int = Field(
        description="``chunk`` + ``chunk_block`` + ``chunk_metadata`` + ``entity_mention`` rows."
    )
    metadata_bytes: int = Field(description="``document_metadata`` rows.")
    observability_bytes: int = Field(description="``job`` + ``job_stage_event`` rows.")
    total_bytes: int = Field(description="Sum of every bucket.")
    estimated: bool = Field(description="Always true: real row bytes, no index/TOAST/bloat.")


class QdrantFootprintModel(BaseModel):
    """
    ESTIMATED vector-store bytes (points x declared shape — excludes HNSW index overhead).

    Attributes:
        points (int): Point count (collection total, or a document's points).
        dense_bytes (int): On-disk float32 dense bytes, summed per named vector weighted by its
            carrier count. Excludes the int8 quantized RAM-resident copy — this is disk, not RAM.
        sparse_bytes (int): ``points * avg_sparse_entries * 8`` (int32 index + float32 value).
        payload_bytes (int): ``points * avg_payload_json_bytes``.
        total_bytes (int): Sum of dense + sparse + payload.
        estimated (bool): Always true: count-based, excludes index overhead.
    """

    points: int = Field(description="Point count (collection total, or a document's points).")
    dense_bytes: int = Field(
        description=(
            "On-disk float32 dense bytes, summed per named vector weighted by its carrier count "
            "(content_dense on every point, each meta vector only on its field's documents). "
            "Excludes the int8 quantized RAM-resident copy — this is disk, not RAM."
        )
    )
    sparse_bytes: int = Field(
        description="``points x avg_sparse_entries x 8`` (int32 index + float32 value)."
    )
    payload_bytes: int = Field(description="``points x avg_payload_json_bytes``.")
    total_bytes: int = Field(description="Sum of dense + sparse + payload.")
    estimated: bool = Field(description="Always true: count-based, excludes index overhead.")


class DocumentStorageModel(BaseModel):
    """
    One document's footprint across the three stores.

    Attributes:
        document_id (str): The document's UUID.
        filename (str): The document's display name.
        s3 (S3FootprintModel): EXACT S3 bytes.
        postgres (PostgresFootprintModel): ESTIMATED Postgres row bytes.
        qdrant (QdrantFootprintModel): ESTIMATED vector-store bytes.
        total_bytes (int): S3 (logical) + Postgres + Qdrant.
    """

    document_id: str = Field(description="The document's UUID.")
    filename: str = Field(description="The document's display name.")
    s3: S3FootprintModel = Field(description="EXACT S3 bytes.")
    postgres: PostgresFootprintModel = Field(description="ESTIMATED Postgres row bytes.")
    qdrant: QdrantFootprintModel = Field(description="ESTIMATED vector-store bytes.")
    total_bytes: int = Field(description="S3 (logical) + Postgres + Qdrant.")


class CollectionStorageResponse(BaseModel):
    """
    A collection's material footprint per store, plus the per-document breakdown (heaviest first).

    S3 bytes are EXACT; Postgres and Qdrant bytes are ESTIMATES (each section flags this via its own
    ``estimated``). ``grand_total_bytes`` uses the DEDUPED S3 disk cost (``physical_unique_bytes``),
    so it reflects real hardware rather than the logical per-document sum.

    Attributes:
        collection_id (str): The measured collection's UUID.
        s3 (S3FootprintModel): EXACT S3 totals (logical + deduped physical).
        postgres (PostgresFootprintModel): ESTIMATED Postgres row bytes.
        qdrant (QdrantFootprintModel): ESTIMATED vector-store bytes.
        grand_total_bytes (int): Material footprint — S3 physical_unique + Postgres + Qdrant.
        documents (list[DocumentStorageModel]): Per-document breakdown, sorted by total bytes
            descending (doubles as top-N).
    """

    collection_id: str = Field(description="The measured collection's UUID.")
    s3: S3FootprintModel = Field(description="EXACT S3 totals (logical + deduped physical).")
    postgres: PostgresFootprintModel = Field(description="ESTIMATED Postgres row bytes.")
    qdrant: QdrantFootprintModel = Field(description="ESTIMATED vector-store bytes.")
    grand_total_bytes: int = Field(
        description="Material footprint — S3 physical_unique + Postgres + Qdrant."
    )
    documents: list[DocumentStorageModel] = Field(
        description="Per-document breakdown, sorted by total bytes descending (doubles as top-N)."
    )


__all__ = [
    "S3FootprintModel",
    "PostgresFootprintModel",
    "QdrantFootprintModel",
    "DocumentStorageModel",
    "CollectionStorageResponse",
]
