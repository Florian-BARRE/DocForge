# ====== Code Summary ======
# RowDeserializer — a bundle JSONL dict → an ORM row, with every id REMAPPED through the import's
# RemapContext (fresh ids so a bundle restores anywhere, incl. its origin server). The chunk's new
# UUID is reused verbatim as its Qdrant point id (kept consistent by the importer when it rewrites
# points.jsonl), so chunk.id == point.id still holds — now on the NEW ids. Enum strings are coerced
# back to their domain StrEnum, and metadata rows re-link to the freshly-minted autoincrement field
# id by field NAME. Blob rows are content-addressed (sha256) and pass through unremapped.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.tables import (
    AttemptStatus,
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
    EnrichmentAttempt,
    EnrichmentKind,
    EnrichmentStatus,
    EntityMention,
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

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RowDeserializer is a static-only class and cannot be instantiated.")

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

    @staticmethod
    def document_metadata(data: dict[str, Any], ctx: RemapContext) -> DocumentMetadata | None:
        """A document-scope value — document + field id remapped, or dropped if the field vanished."""
        field_id = ctx.field_ids.get(data["field_name"])
        if field_id is None:
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

    @staticmethod
    def block(data: dict[str, Any], ctx: RemapContext) -> Block:
        """An IR block — re-namespaced string id, document + parent remapped."""
        return Block(
            id=ctx.blocks[data["id"]],
            document_id=ctx.documents[data["document_id"]],
            block_type=data["block_type"],
            page=data["page"],
            bbox=list(data["bbox"]),
            reading_order=data["reading_order"],
            column_index=data["column_index"],
            parent_id=ctx.blocks.get(data["parent_id"]) if data["parent_id"] else None,
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

    @staticmethod
    def block_figure(data: dict[str, Any], ctx: RemapContext) -> BlockFigure:
        """A figure detail row — block + caption block remapped (crop hash unchanged)."""
        caption = data["caption_block_id"]
        return BlockFigure(
            block_id=ctx.blocks[data["block_id"]],
            crop_blob_hash=data["crop_blob_hash"],
            caption_block_id=ctx.blocks.get(caption) if caption else None,
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

    @staticmethod
    def enrichment_attempt(data: dict[str, Any], ctx: RemapContext) -> EnrichmentAttempt:
        """One escalation-chain attempt — fresh id, enrichment remapped."""
        return EnrichmentAttempt(
            id=ctx.attempts[data["id"]],
            block_enrichment_id=ctx.enrichments[data["block_enrichment_id"]],
            position=data["position"],
            capability=data["capability"],
            provider_id=data["provider_id"],
            model=data["model"],
            status=AttemptStatus(data["status"]),
            error=data["error"],
            latency_ms=data["latency_ms"],
        )

    @staticmethod
    def chunk(data: dict[str, Any], ctx: RemapContext) -> Chunk:
        """A chunk — fresh id (reused as its Qdrant point id), document + parent remapped."""
        parent = data["parent_id"]
        return Chunk(
            id=ctx.chunks[data["id"]],
            document_id=ctx.documents[data["document_id"]],
            config_hash=data["config_hash"],
            chunk_index=data["chunk_index"],
            strategy=data["strategy"],
            parent_id=ctx.chunks.get(parent) if parent else None,
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

    @staticmethod
    def chunk_metadata(data: dict[str, Any], ctx: RemapContext) -> ChunkMetadata | None:
        """A chunk-scope value — chunk + field id remapped, or dropped if the field vanished."""
        field_id = ctx.field_ids.get(data["field_name"])
        if field_id is None:
            return None
        return ChunkMetadata(
            chunk_id=ctx.chunks[data["chunk_id"]],
            field_id=field_id,
            value=data["value"],
            origin=FieldOrigin(data["origin"]),
        )

    @staticmethod
    def entity_mention(data: dict[str, Any], ctx: RemapContext) -> EntityMention:
        """A named entity — fresh id, chunk remapped."""
        return EntityMention(
            id=ctx.entities[data["id"]],
            chunk_id=ctx.chunks[data["chunk_id"]],
            entity_type=data["entity_type"],
            surface_text=data["surface_text"],
            normalized_value=data["normalized_value"],
            span=data["span"],
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
