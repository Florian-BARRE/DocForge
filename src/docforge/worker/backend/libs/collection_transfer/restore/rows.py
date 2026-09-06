# ====== Code Summary ======
# RowDeserializer — a bundle JSONL dict → an ORM row, with every id REMAPPED through the import's
# RemapContext (fresh ids so a bundle restores anywhere, incl. its origin server). The chunk's new
# UUID is reused verbatim as its Qdrant point id (kept consistent by the importer when it rewrites
# points.jsonl), so chunk.id == point.id still holds — now on the NEW ids. Enum strings are coerced
# back to their domain StrEnum, and metadata rows re-link to the freshly-minted autoincrement field
# id by field NAME. Blob rows are content-addressed (sha256) and pass through unremapped.
#
# Dangling-reference policy (uniform + honest, never a silent wrong value):
#   * PRIMARY foreign keys (a row's own owner: block/chunk/page.document_id, chunk_block ends, …) are
#     required — a missing target means a structurally corrupt bundle, so they FAIL LOUD (KeyError).
#   * OPTIONAL structural links (block/chunk parent_id, figure caption_block_id) are recoverable: a
#     dangling target is LOGGED (warning, naming the id) and DROPPED to NULL — the import proceeds.
#   * An UNKNOWN metadata field (no matching field in the restored schema) is LOGGED and the value is
#     SKIPPED (returns None). The stale point-payload document_id is handled the same way in the importer.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.tables import (
    Blob,
    BlobKind,
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Chunk,
    ChunkBlock,
    ChunkMetadata,
    Document,
    DocumentMetadata,
    DocumentStatus,
    EnrichmentKind,
    EnrichmentStatus,
    MetadataField,
    Page,
    SourceKind,
)

# ====== Local Project Imports ======
from .remap import RemapContext


def _dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp back, tolerating a missing/blank value."""
    return datetime.fromisoformat(value) if value else None


class RowDeserializer:
    """Static per-table bundle-dict → ORM-row deserialization (ids remapped via RemapContext)."""

    logger = loggerplusplus.bind(identifier="RowDeserializer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RowDeserializer is a static-only class and cannot be instantiated.")

    @classmethod
    def _optional_ref(cls, old_id: Any, mapping: dict[str, Any], *, label: str) -> Any | None:
        """
        Remap an OPTIONAL self-link (block/chunk parent, figure caption), logging + dropping danglers.

        Args:
            old_id (Any): The referenced source id, or None/empty when there is no link.
            mapping (dict[str, Any]): The relevant old→new id map (``ctx.blocks`` or ``ctx.chunks``).
            label (str): A human label for the link kind (used in the warning).

        Returns:
            Any | None: The remapped id, or None when absent or dangling (dropped to NULL).
        """
        # 1. No link at all — nothing to remap.
        if not old_id:
            return None

        # 2. A present-but-unknown target is a recoverable dangling link: log it and drop to NULL.
        new_id = mapping.get(old_id)
        if new_id is None:
            cls.logger.warning(
                f"Dangling {label} reference '{old_id}' in bundle (no such row restored) — "
                f"dropping the link to NULL; import proceeds."
            )
        return new_id

    @staticmethod
    def metadata_field(data: dict[str, Any]) -> MetadataField:
        """A schema field WITHOUT id/collection_id (both assigned when the collection is created)."""
        return MetadataField(
            field_name=data["field_name"],
            field_type=FieldType(data["field_type"]),
            required=data["required"],
            filterable=data["filterable"],
            lexical=data["lexical"],
            semantic=data["semantic"],
            enum_values=data["enum_values"],
            origin=FieldOrigin(data["origin"]),
            scope=FieldScope(data["scope"]),
        )

    @staticmethod
    def document(data: dict[str, Any], collection_id: uuid.UUID, ctx: RemapContext) -> Document:
        """A catalogue record — a FRESH id, rehomed onto the NEW collection."""
        return Document(
            id=ctx.documents[data["id"]],
            collection_id=collection_id,
            source_hash=data["source_hash"],
            pdf_blob_hash=data["pdf_blob_hash"],
            filename=data["filename"],
            format=data["format"],
            mime_type=data["mime_type"],
            file_size=data["file_size"],
            page_count=data["page_count"],
            language=data["language"],
            source_kind=SourceKind(data["source_kind"]),
            title=data["title"],
            simhash=data["simhash"],
            status=DocumentStatus(data["status"]),
            pipeline_version=data["pipeline_version"],
            enabled=data["enabled"],
            created_at=_dt(data.get("created_at")),
        )

    @classmethod
    def document_metadata(cls, data: dict[str, Any], ctx: RemapContext) -> DocumentMetadata | None:
        """A document-scope value — document + field id remapped, or logged+dropped if unknown."""
        field_id = ctx.field_ids.get(data["field_name"])
        if field_id is None:
            cls.logger.warning(
                f"Unknown document metadata field '{data['field_name']}' in bundle (no matching "
                f"field in the restored schema) — skipping the value; import proceeds."
            )
            return None
        return DocumentMetadata(
            document_id=ctx.documents[data["document_id"]],
            field_id=field_id,
            value=data["value"],
            origin=FieldOrigin(data["origin"]),
        )

    @staticmethod
    def page(data: dict[str, Any], ctx: RemapContext) -> Page:
        """A page row — fresh id, document remapped."""
        return Page(
            id=ctx.pages[data["id"]],
            document_id=ctx.documents[data["document_id"]],
            page_number=data["page_number"],
            width=data["width"],
            height=data["height"],
            is_scanned=data["is_scanned"],
            language=data["language"],
            render_blob_hash=data["render_blob_hash"],
        )

    @classmethod
    def block(cls, data: dict[str, Any], ctx: RemapContext) -> Block:
        """An IR block — re-namespaced string id, document + (optional) parent remapped."""
        return Block(
            id=ctx.blocks[data["id"]],
            document_id=ctx.documents[data["document_id"]],
            block_type=data["block_type"],
            page=data["page"],
            bbox=list(data["bbox"]),
            reading_order=data["reading_order"],
            column_index=data["column_index"],
            parent_id=cls._optional_ref(data["parent_id"], ctx.blocks, label="block parent"),
            level=data["level"],
            text=data["text"],
            is_boilerplate=data["is_boilerplate"],
            language=data["language"],
            confidence=data["confidence"],
        )

    @staticmethod
    def block_table(data: dict[str, Any], ctx: RemapContext) -> BlockTable:
        """A table detail row — block remapped."""
        return BlockTable(
            block_id=ctx.blocks[data["block_id"]],
            n_rows=data["n_rows"],
            n_cols=data["n_cols"],
            has_header=data["has_header"],
            cells=data["cells"],
            linearized_md=data["linearized_md"],
        )

    @classmethod
    def block_figure(cls, data: dict[str, Any], ctx: RemapContext) -> BlockFigure:
        """A figure detail row — block + (optional) caption block remapped (crop hash unchanged)."""
        return BlockFigure(
            block_id=ctx.blocks[data["block_id"]],
            crop_blob_hash=data["crop_blob_hash"],
            caption_block_id=cls._optional_ref(
                data["caption_block_id"], ctx.blocks, label="figure caption"
            ),
        )

    @staticmethod
    def block_enrichment(data: dict[str, Any], ctx: RemapContext) -> BlockEnrichment:
        """An enrichment row — fresh id, block remapped."""
        return BlockEnrichment(
            id=ctx.enrichments[data["id"]],
            block_id=ctx.blocks[data["block_id"]],
            kind=EnrichmentKind(data["kind"]),
            text=data["text"],
            data=data["data"],
            status=EnrichmentStatus(data["status"]),
        )

    @classmethod
    def chunk(cls, data: dict[str, Any], ctx: RemapContext) -> Chunk:
        """A chunk — fresh id (reused as its Qdrant point id), document + (optional) parent remapped."""
        return Chunk(
            id=ctx.chunks[data["id"]],
            document_id=ctx.documents[data["document_id"]],
            config_hash=data["config_hash"],
            chunk_index=data["chunk_index"],
            strategy=data["strategy"],
            parent_id=cls._optional_ref(data["parent_id"], ctx.chunks, label="chunk parent"),
            text=data["text"],
            token_count=data["token_count"],
            heading_path=data["heading_path"],
            simhash=data["simhash"],
            is_indexed=data["is_indexed"],
            role=data["role"],
            enabled_override=data["enabled_override"],
            created_at=_dt(data.get("created_at")),
        )

    @staticmethod
    def chunk_block(data: dict[str, Any], ctx: RemapContext) -> ChunkBlock:
        """A chunk ↔ block membership — both sides remapped."""
        return ChunkBlock(
            chunk_id=ctx.chunks[data["chunk_id"]],
            block_id=ctx.blocks[data["block_id"]],
            position=data["position"],
        )

    @classmethod
    def chunk_metadata(cls, data: dict[str, Any], ctx: RemapContext) -> ChunkMetadata | None:
        """A chunk-scope value — chunk + field id remapped, or logged+dropped if the field is unknown."""
        field_id = ctx.field_ids.get(data["field_name"])
        if field_id is None:
            cls.logger.warning(
                f"Unknown chunk metadata field '{data['field_name']}' in bundle (no matching field "
                f"in the restored schema) — skipping the value; import proceeds."
            )
            return None
        return ChunkMetadata(
            chunk_id=ctx.chunks[data["chunk_id"]],
            field_id=field_id,
            value=data["value"],
            origin=FieldOrigin(data["origin"]),
        )

    @staticmethod
    def blob(data: dict[str, Any]) -> Blob:
        """A blob registry row — content-addressed (sha256), NOT remapped."""
        return Blob(
            content_hash=data["content_hash"],
            s3_key=data["s3_key"],
            mime_type=data["mime_type"],
            size_bytes=data["size_bytes"],
            kind=BlobKind(data["kind"]),
        )


__all__ = ["RowDeserializer"]
