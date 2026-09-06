# ====== Code Summary ======
# ExplorerHelpers — the ORM-row → response-model mapping for the document explorer. Kept out of
# router.py so the routes stay pure orchestration (facade calls + 404 guards). Metadata rows carry a
# field_id, not a name, so mapping resolves names against the collection schema (built once per
# request into a {field_id: field_name} map).

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import ChunkRole, role_default_enabled
from shared_libs.services.db.facades import ChunkToggle, IRBundle
from shared_libs.services.db.postgresql.tables import (
    Chunk,
    ChunkMetadata,
    Document,
    DocumentMetadata,
    MetadataField,
    Page,
)

# ====== Local Project Imports ======
from .models import (
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    MetadataValue,
    PageInfo,
)
from .models_ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable


class ExplorerHelpers:
    """Static mapping helpers turning stored rows into the explorer's response models."""

    logger = loggerplusplus.bind(identifier="ExplorerHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ExplorerHelpers is a static-only class and cannot be instantiated.")

    # -------------------- metadata --------------------
    @staticmethod
    def field_names(schema: Sequence[MetadataField]) -> dict[int, str]:
        """Build the {field_id: field_name} map used to resolve metadata values."""
        return {row.id: row.field_name for row in schema}

    @classmethod
    def metadata_values(
        cls,
        rows: Sequence[DocumentMetadata | ChunkMetadata],
        names: dict[int, str],
    ) -> list[MetadataValue]:
        """Resolve each metadata row's field name (falling back to the id if the schema drifted)."""
        return [
            MetadataValue(
                field_name=names.get(row.field_id, f"field_{row.field_id}"),
                value=row.value,
                origin=row.origin,
            )
            for row in rows
        ]

    # -------------------- documents --------------------
    @staticmethod
    def list_item(document: Document) -> DocumentListItem:
        """Map a document row to a catalogue list item."""
        return DocumentListItem(
            id=str(document.id),
            filename=document.filename,
            format=document.format,
            status=document.status,
            page_count=document.page_count,
            file_size=document.file_size,
            created_at=document.created_at,
            title=document.title,
            language=document.language,
            enabled=document.enabled,
        )

    @staticmethod
    def detail(document: Document, metadata: list[MetadataValue]) -> DocumentDetail:
        """Map a document row + resolved metadata to the full detail model."""
        return DocumentDetail(
            id=str(document.id),
            collection_id=str(document.collection_id),
            filename=document.filename,
            format=document.format,
            mime_type=document.mime_type,
            file_size=document.file_size,
            page_count=document.page_count,
            language=document.language,
            title=document.title,
            source_kind=document.source_kind,
            status=document.status,
            source_hash=document.source_hash,
            pdf_blob_hash=document.pdf_blob_hash,
            simhash=document.simhash,
            pipeline_version=document.pipeline_version,
            created_at=document.created_at,
            enabled=document.enabled,
            metadata=metadata,
        )

    # -------------------- pages --------------------
    @staticmethod
    def page(page: Page) -> PageInfo:
        """Map a page row to its explorer model."""
        return PageInfo(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            is_scanned=page.is_scanned,
            language=page.language,
            render_blob_hash=page.render_blob_hash,
        )

    # -------------------- IR --------------------
    @classmethod
    def ir(cls, bundle: IRBundle) -> DocumentIRModel:
        """Map the full IR bundle (raw blocks + details + enrichments) to its response model."""
        return DocumentIRModel(
            blocks=[
                IRBlock(
                    id=block.id,
                    block_type=block.block_type,
                    page=block.page,
                    bbox=list(block.bbox),
                    reading_order=block.reading_order,
                    parent_id=block.parent_id,
                    level=block.level,
                    text=block.text,
                    is_boilerplate=block.is_boilerplate,
                    language=block.language,
                )
                for block in bundle.blocks
            ],
            tables=[
                IRTable(
                    block_id=table.block_id,
                    n_rows=table.n_rows,
                    n_cols=table.n_cols,
                    has_header=table.has_header,
                    cells=table.cells,
                    linearized_md=table.linearized_md,
                )
                for table in bundle.tables
            ],
            figures=[
                IRFigure(
                    block_id=figure.block_id,
                    crop_blob_hash=figure.crop_blob_hash,
                    caption_block_id=figure.caption_block_id,
                )
                for figure in bundle.figures
            ],
            enrichments=[
                IREnrichment(
                    id=str(enrichment.id),
                    block_id=enrichment.block_id,
                    kind=enrichment.kind,
                    text=enrichment.text,
                    data=enrichment.data,
                    status=enrichment.status,
                )
                for enrichment in bundle.enrichments
            ],
        )

    # -------------------- chunks --------------------
    @classmethod
    def chunk(
        cls,
        chunk: Chunk,
        block_ids: list[str],
        metadata: list[MetadataValue],
        page: int | None,
    ) -> ChunkInfo:
        """Map a chunk row + its composition, metadata and resolved page to the explorer model."""
        return ChunkInfo(
            id=str(chunk.id),
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            is_indexed=chunk.is_indexed,
            strategy=chunk.strategy,
            parent_id=str(chunk.parent_id) if chunk.parent_id is not None else None,
            block_ids=block_ids,
            metadata=metadata,
            role=chunk.role,
            enabled=cls._effective_enabled(chunk),
            heading_path=chunk.heading_path or [],
            page=page,
        )

    @classmethod
    def _effective_enabled(cls, chunk: Chunk) -> bool:
        """Resolve a chunk's effective searchability: the user override wins, else the role default."""
        # 1. An explicit user override always wins over the structural default.
        if chunk.enabled_override is not None:
            return chunk.enabled_override

        # 2. No override — defer to the single role -> default-enabled policy. The role column is a
        #    plain VARCHAR, so an unknown forward-compat/legacy value must degrade (treated as a
        #    non-body role: disabled by default) rather than 500 the whole chunk read.
        try:
            role = ChunkRole(chunk.role)
        except ValueError:
            cls.logger.warning(
                f"Unknown chunk role '{chunk.role}' on chunk {chunk.id}; defaulting to disabled"
            )
            return False
        return role_default_enabled(role)

    @staticmethod
    def chunk_toggle(
        outcome: ChunkToggle,
        *,
        search_sync_pending: bool = False,
        search_sync_error: str | None = None,
    ) -> ChunkEnabledResult:
        """
        Map a facade toggle outcome to its response model (effective state + reindex flag).

        The search-store sync signal is passed only by the single-chunk route (where this result is
        the whole response); a bulk response carries it at the request level, so its nested per-chunk
        results keep the defaults.
        """
        return ChunkEnabledResult(
            chunk_id=str(outcome.chunk_id),
            enabled=outcome.enabled,
            reindex_required=outcome.reindex_required,
            search_sync_pending=search_sync_pending,
            search_sync_error=search_sync_error,
        )


__all__ = ["ExplorerHelpers"]
