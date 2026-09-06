# ====== Code Summary ======
# BundlePaths — the ONE place the `.dcexport` layout is spelled out: the fixed top-level files, the
# per-table JSONL paths under ``postgres/``, the Qdrant points file, the schema file and the blob
# directory. Both the writer and the reader import these constants so the on-disk contract can never
# drift between the two sides.

# ====== Standard Library Imports ======
from __future__ import annotations


class BundlePaths:
    """Static registry of the `.dcexport` bundle's internal paths (writer + reader share it)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BundlePaths is a static-only class and cannot be instantiated.")

    # ── Top-level ──
    MANIFEST = "manifest.json"
    COLLECTION = "collection.json"

    # ── Schema ──
    METADATA_FIELDS = "schema/metadata_fields.jsonl"

    # ── Postgres tables (streamed JSONL, one per table) ──
    DOCUMENTS = "postgres/documents.jsonl"
    DOCUMENT_METADATA = "postgres/document_metadata.jsonl"
    PAGES = "postgres/pages.jsonl"
    IR_BLOCKS = "postgres/ir_blocks.jsonl"
    IR_TABLES = "postgres/ir_tables.jsonl"
    IR_FIGURES = "postgres/ir_figures.jsonl"
    IR_ENRICHMENTS = "postgres/ir_enrichments.jsonl"
    CHUNKS = "postgres/chunks.jsonl"
    CHUNK_BLOCKS = "postgres/chunk_blocks.jsonl"
    CHUNK_METADATA = "postgres/chunk_metadata.jsonl"
    BLOBS = "postgres/blobs.jsonl"

    # ── Qdrant ──
    POINTS = "qdrant/points.jsonl"

    # ── Blob bytes (one file per unique sha256) ──
    BLOB_DIR = "blobs"

    @staticmethod
    def blob_path(content_hash: str) -> str:
        """The in-bundle path of a blob's raw bytes (one file per unique hash)."""
        return f"{BundlePaths.BLOB_DIR}/{content_hash}"


# Every fixed (non-blob) file the manifest checksums, in dependency/restore order.
ORDERED_DATA_FILES = (
    BundlePaths.METADATA_FIELDS,
    BundlePaths.DOCUMENTS,
    BundlePaths.DOCUMENT_METADATA,
    BundlePaths.PAGES,
    BundlePaths.IR_BLOCKS,
    BundlePaths.IR_TABLES,
    BundlePaths.IR_FIGURES,
    BundlePaths.IR_ENRICHMENTS,
    BundlePaths.CHUNKS,
    BundlePaths.CHUNK_BLOCKS,
    BundlePaths.CHUNK_METADATA,
    BundlePaths.BLOBS,
    BundlePaths.POINTS,
)


__all__ = ["BundlePaths", "ORDERED_DATA_FILES"]
