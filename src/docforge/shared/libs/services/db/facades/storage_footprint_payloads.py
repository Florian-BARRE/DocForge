# ====== Code Summary ======
# The transfer objects the StorageFootprintFacade returns: a collection's material footprint across
# the three stores, plus the per-document breakdown (sorted, so it doubles as the top-N). S3 bytes
# are EXACT (from the content-addressed blob registry); Postgres and Qdrant bytes are ESTIMATES
# (real row bytes via pg_column_size / count-times-shape arithmetic) — the models name that honestly
# via the ``estimated`` flag so a caller never mistakes an estimate for a measured truth.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class S3Footprint:
    """EXACT S3 bytes (from the blob registry). Per document: its own blobs, deduped.

    Attributes:
        original_bytes (int): The uploaded source file(s).
        rendered_bytes (int): Derived blobs — canonical PDF, page renders, figure crops.
        total_bytes (int): ``original + rendered`` (a document's logical byte usage).
        physical_unique_bytes (int): Deduped disk cost. At collection level a blob shared by two
            documents counts once (so ``physical_unique <= total``); per document it equals ``total``.
    """

    original_bytes: int
    rendered_bytes: int
    total_bytes: int
    physical_unique_bytes: int
    estimated: bool = False


@dataclass(slots=True)
class PostgresFootprint:
    """ESTIMATED on-disk row bytes of the exploded IR (``pg_column_size`` per row — no index/TOAST).

    Attributes:
        documents_bytes (int): ``document`` + ``page`` rows.
        ir_blocks_bytes (int): ``block`` + ``block_table`` + ``block_figure`` rows.
        enrichment_bytes (int): ``block_enrichment`` rows.
        chunks_bytes (int): ``chunk`` + ``chunk_block`` + ``chunk_metadata`` rows.
        metadata_bytes (int): ``document_metadata`` rows.
        observability_bytes (int): ``job`` + ``job_stage_event`` rows.
        total_bytes (int): The sum of every bucket above.
    """

    documents_bytes: int
    ir_blocks_bytes: int
    enrichment_bytes: int
    chunks_bytes: int
    metadata_bytes: int
    observability_bytes: int
    total_bytes: int
    estimated: bool = True


@dataclass(slots=True)
class QdrantFootprint:
    """ESTIMATED vector-store bytes (points × declared shape — excludes HNSW index overhead).

    Attributes:
        points (int): Point count (collection total, or a document's points).
        dense_bytes (int): On-disk float32 dense bytes, summed PER named vector weighted by its own
            carrier count: ``Σ_vector (carrier_points × dim × 4)`` — ``content_dense`` on every point,
            a ``meta_<slug>_dense`` only on its field's documents. Measures the on-disk float32 copy;
            the int8 scalar-quantized copy Qdrant keeps resident in RAM (+1 B/dim) is EXCLUDED (this
            is a disk footprint, not a RAM one).
        sparse_bytes (int): ``points × avg_sparse_entries × 8`` (int32 index + float32 value).
        payload_bytes (int): ``points × avg_payload_json_bytes``.
        total_bytes (int): The sum of dense + sparse + payload.
    """

    points: int
    dense_bytes: int
    sparse_bytes: int
    payload_bytes: int
    total_bytes: int
    estimated: bool = True


@dataclass(slots=True)
class DocumentFootprint:
    """One document's footprint across the three stores."""

    document_id: uuid.UUID
    filename: str
    s3: S3Footprint
    postgres: PostgresFootprint
    qdrant: QdrantFootprint
    total_bytes: int


@dataclass(slots=True)
class CollectionFootprint:
    """A collection's material footprint: per-store totals + the per-document breakdown (top-N first).

    Attributes:
        collection_id (uuid.UUID): The measured collection.
        s3 (S3Footprint): EXACT S3 totals; ``total_bytes`` is the logical sum, ``physical_unique_bytes``
            the deduped disk cost.
        postgres (PostgresFootprint): ESTIMATED Postgres row bytes.
        qdrant (QdrantFootprint): ESTIMATED vector-store bytes.
        grand_total_bytes (int): The material footprint — S3 ``physical_unique`` + Postgres + Qdrant.
        documents (list[DocumentFootprint]): Per-document breakdown, sorted by total bytes descending.
    """

    collection_id: uuid.UUID
    s3: S3Footprint
    postgres: PostgresFootprint
    qdrant: QdrantFootprint
    grand_total_bytes: int
    documents: list[DocumentFootprint] = field(default_factory=list)


__all__ = [
    "S3Footprint",
    "PostgresFootprint",
    "QdrantFootprint",
    "DocumentFootprint",
    "CollectionFootprint",
]
