# ====== Code Summary ======
# RowSerializer — turns one ORM row (or a Qdrant record) into the plain JSON-able dict a bundle
# JSONL line carries. Every globally-unique id (document/chunk/page/block/enrichment/entity UUID and
# the string block id) is emitted AS-IS into the bundle purely as a stable JOIN KEY between the
# bundle's files — the IMPORT then REGENERATES every id and rewrites all foreign keys (see
# restore/remap.py + restore/rows.py), so nothing is "preserved" onto the restored collection. The
# ids only need to be internally consistent within the bundle (e.g. the chunk id here becomes the
# Qdrant point id, and the importer remaps both together). The autoincrement metadata field id is
# deliberately NOT emitted: metadata rows travel keyed by field NAME (resolved upstream) so the
# bundle survives the target re-assigning integer keys. Qdrant vectors split dense (list) vs sparse.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import Enum
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import (
    Blob,
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    Document,
    MetadataField,
    Page,
)
from shared_libs.services.db.qdrant import SparseVec


def _enum(value: Any) -> Any:
    """Emit a StrEnum's VALUE (its string), leaving plain values untouched."""
    return value.value if isinstance(value, Enum) else value


def _dt(value: Any) -> str | None:
    """ISO-8601 a timestamp column, or None."""
    return value.isoformat() if value is not None else None


class RowSerializer:
    """Static per-table ORM-row → bundle-dict serialization (ids emitted as join keys, remapped on import)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RowSerializer is a static-only class and cannot be instantiated.")

    @staticmethod
    def metadata_field(row: MetadataField) -> dict[str, Any]:
        """Schema field — NO id (re-minted on import; values re-link by name)."""
        return {
            "field_name": row.field_name,
            "field_type": _enum(row.field_type),
            "required": row.required,
            "filterable": row.filterable,
            "lexical": row.lexical,
            "semantic": row.semantic,
            "enum_values": row.enum_values,
            "origin": _enum(row.origin),
            "scope": _enum(row.scope),
        }

    @staticmethod
    def document(row: Document) -> dict[str, Any]:
        """The catalogue record — id emitted as a bundle join key (remapped on import)."""
        return {
            "id": str(row.id),
            "source_hash": row.source_hash,
            "pdf_blob_hash": row.pdf_blob_hash,
            "filename": row.filename,
            "format": row.format,
            "mime_type": row.mime_type,
            "file_size": row.file_size,
            "page_count": row.page_count,
            "language": row.language,
            "source_kind": _enum(row.source_kind),
            "title": row.title,
            "simhash": row.simhash,
            "status": _enum(row.status),
            "pipeline_version": row.pipeline_version,
            "enabled": row.enabled,
            "created_at": _dt(row.created_at),
        }

    @staticmethod
    def document_metadata(
        document_id: Any, field_name: str, value: Any, origin: Any
    ) -> dict[str, Any]:
        """A document-scope value keyed by field NAME (not the server-local field id)."""
        return {
            "document_id": str(document_id),
            "field_name": field_name,
            "value": value,
            "origin": _enum(origin),
        }

    @staticmethod
    def page(row: Page) -> dict[str, Any]:
        """A page row — id emitted as a bundle join key (remapped on import)."""
        return {
            "id": str(row.id),
            "document_id": str(row.document_id),
            "page_number": row.page_number,
            "width": row.width,
            "height": row.height,
            "is_scanned": row.is_scanned,
            "language": row.language,
            "render_blob_hash": row.render_blob_hash,
        }

    @staticmethod
    def block(row: Block) -> dict[str, Any]:
        """An IR block — string id emitted as a bundle join key (re-namespaced onto the new doc on import)."""
        return {
            "id": row.id,
            "document_id": str(row.document_id),
            "block_type": row.block_type,
            "page": row.page,
            "bbox": list(row.bbox),
            "reading_order": row.reading_order,
            "column_index": row.column_index,
            "parent_id": row.parent_id,
            "level": row.level,
            "text": row.text,
            "is_boilerplate": row.is_boilerplate,
            "language": row.language,
            "confidence": row.confidence,
        }

    @staticmethod
    def block_table(row: BlockTable) -> dict[str, Any]:
        """A table detail row (1:1 with its block)."""
        return {
            "block_id": row.block_id,
            "n_rows": row.n_rows,
            "n_cols": row.n_cols,
            "has_header": row.has_header,
            "cells": row.cells,
            "linearized_md": row.linearized_md,
        }

    @staticmethod
    def block_figure(row: BlockFigure) -> dict[str, Any]:
        """A figure detail row (1:1 with its block)."""
        return {
            "block_id": row.block_id,
            "crop_blob_hash": row.crop_blob_hash,
            "caption_block_id": row.caption_block_id,
        }

    @staticmethod
    def block_enrichment(row: BlockEnrichment) -> dict[str, Any]:
        """An enrichment row — id emitted as a bundle join key (remapped on import)."""
        return {
            "id": str(row.id),
            "block_id": row.block_id,
            "kind": _enum(row.kind),
            "text": row.text,
            "data": row.data,
            "status": _enum(row.status),
        }

    @staticmethod
    def chunk(row: Chunk) -> dict[str, Any]:
        """A chunk — id emitted as a bundle join key (== its Qdrant point id; both remapped on import)."""
        return {
            "id": str(row.id),
            "document_id": str(row.document_id),
            "config_hash": row.config_hash,
            "chunk_index": row.chunk_index,
            "strategy": row.strategy,
            "parent_id": str(row.parent_id) if row.parent_id else None,
            "text": row.text,
            "token_count": row.token_count,
            "heading_path": list(row.heading_path) if row.heading_path else None,
            "simhash": row.simhash,
            "is_indexed": row.is_indexed,
            "role": row.role,
            "enabled_override": row.enabled_override,
            "created_at": _dt(row.created_at),
        }

    @staticmethod
    def chunk_block(row: ChunkBlock) -> dict[str, Any]:
        """A chunk ↔ block membership, ordered."""
        return {
            "chunk_id": str(row.chunk_id),
            "block_id": row.block_id,
            "position": row.position,
        }

    @staticmethod
    def chunk_metadata(chunk_id: Any, field_name: str, value: Any, origin: Any) -> dict[str, Any]:
        """A chunk-scope value keyed by field NAME (not the server-local field id)."""
        return {
            "chunk_id": str(chunk_id),
            "field_name": field_name,
            "value": value,
            "origin": _enum(origin),
        }

    @staticmethod
    def blob(row: Blob) -> dict[str, Any]:
        """A blob registry row (the bytes travel separately under blobs/<hash>)."""
        return {
            "content_hash": row.content_hash,
            "s3_key": row.s3_key,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "kind": _enum(row.kind),
        }

    @staticmethod
    def point(record: Any) -> dict[str, Any]:
        """A Qdrant record → {id, vectors, payload}, splitting dense (list) vs sparse ({...})."""
        vectors: dict[str, Any] = {}
        raw_vectors = record.vector or {}
        for name, vector in raw_vectors.items():
            if isinstance(vector, SparseVec) or hasattr(vector, "indices"):
                vectors[name] = {
                    "indices": list(vector.indices),
                    "values": list(vector.values),
                }
            else:
                vectors[name] = list(vector)
        return {"id": str(record.id), "vectors": vectors, "payload": record.payload or {}}


__all__ = ["RowSerializer"]
