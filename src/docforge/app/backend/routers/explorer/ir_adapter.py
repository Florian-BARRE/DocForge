# ====== Code Summary ======
# IRBundleAdapter — the READ-side persistence→domain adapter that reconstructs the canonical
# DocumentIR from the DB-shaped IRBundle (Block / BlockTable / BlockFigure / BlockEnrichment rows).
# It is the mirror of the worker's IR→DB translator (which runs the other way, at persist time): the
# on-the-fly markdown/HTML views need a DocumentIR, but the explorer endpoint only ever holds rows.
# Enrichment rows are folded back onto each figure's slot, table rows become TableData, and every
# block's reading_order is preserved verbatim — the linearizer folds a figure's caption purely by
# reading-order adjacency (caption_block_id lives only in the DB model, not in DocumentIR).

# ====== Standard Library Imports ======
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    Provenance,
    TableData,
)
from shared_libs.public_models.ir import FigureKind
from shared_libs.services.db.facades import IRBundle
from shared_libs.services.db.postgresql.tables import (
    Block as BlockRow,
)
from shared_libs.services.db.postgresql.tables import (
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Document,
    EnrichmentKind,
    EnrichmentStatus,
)


class IRBundleAdapter:
    """Rebuild a canonical DocumentIR from the DB-shaped IRBundle for on-the-fly linearization."""

    logger = loggerplusplus.bind(identifier="IRBundleAdapter")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IRBundleAdapter is a static-only class and cannot be instantiated.")

    @classmethod
    def to_document_ir(cls, document: Document, bundle: IRBundle) -> DocumentIR:
        """
        Reconstruct the canonical DocumentIR from a document row and its stored IR rows.

        Args:
            document (Document): The document row (supplies doc_id, source_hash and header facts).
            bundle (IRBundle): The stored blocks, tables, figures and enrichments.

        Returns:
            DocumentIR: The canonical IR, blocks in preserved reading order, figure slots folded
                from their table/figure detail rows and enrichment rows.
        """
        # 1. Index the detail + enrichment rows by their owning block id (single pass each).
        tables_by_block = {row.block_id: row for row in bundle.tables}
        figures_by_block = {row.block_id: row for row in bundle.figures}
        enrichments_by_block: dict[str, list[BlockEnrichment]] = defaultdict(list)
        for enrichment in bundle.enrichments:
            enrichments_by_block[enrichment.block_id].append(enrichment)

        # 2. Map every raw block row to its canonical Block, filling the type-specific slot.
        blocks = [
            cls._block(
                row,
                tables_by_block.get(row.id),
                figures_by_block.get(row.id),
                enrichments_by_block.get(row.id, []),
            )
            for row in bundle.blocks
        ]

        # 3. Assemble the document envelope; reading order is carried on each block, not reordered.
        return DocumentIR(
            doc_id=str(document.id),
            source_hash=document.source_hash,
            title=document.title or "",
            n_pages=document.page_count or 0,
            language=document.language or "",
            blocks=blocks,
        )

    @classmethod
    def _block(
        cls,
        row: BlockRow,
        table: BlockTable | None,
        figure: BlockFigure | None,
        enrichments: Sequence[BlockEnrichment],
    ) -> Block:
        """Map one raw block row (plus its detail/enrichment rows) to a canonical Block."""
        # 1. Resolve the semantic type once — it decides which content slot is filled.
        block_type = BlockType(row.block_type)

        # 2. Fill the table slot for TABLE blocks and the figure slot for FIGURE blocks.
        table_data = cls._table(table) if block_type == BlockType.TABLE and table else None
        figure_data = cls._figure(figure, enrichments) if block_type == BlockType.FIGURE else None

        # 3. Build the block, preserving reading order and the heading-tree links verbatim.
        return Block(
            id=row.id,
            block_type=block_type,
            provenance=Provenance(page=row.page, bbox=tuple(row.bbox), char_span=None),
            reading_order=row.reading_order,
            parent_id=row.parent_id,
            level=row.level,
            text=row.text,
            table=table_data,
            figure=figure_data,
            language=row.language,
        )

    @staticmethod
    def _table(table: BlockTable) -> TableData:
        """Map a BlockTable row to the canonical TableData grid."""
        return TableData(
            cells=table.cells,
            n_rows=table.n_rows,
            n_cols=table.n_cols,
            has_header=table.has_header,
        )

    @classmethod
    def _figure(
        cls, figure: BlockFigure | None, enrichments: Sequence[BlockEnrichment]
    ) -> FigureEnrichment:
        """
        Fold a figure's enrichment rows back onto its canonical figure slot.

        The crop bytes are not rehydrated (only the blob hash is stored, and the linearized view
        never renders raw bytes); OCR/VLM/chart-to-data enrichments become the retrieval-facing
        text and data the linearizer emits.
        """
        # 1. Start from parse-time defaults; only successful enrichments carry meaning to fold.
        slot = FigureEnrichment()
        successful = {
            enrichment.kind: enrichment
            for enrichment in enrichments
            if enrichment.status == EnrichmentStatus.OK
        }

        # 2. Refine the visual kind from a CLASSIFY enrichment when it names a known FigureKind.
        classify = successful.get(EnrichmentKind.CLASSIFY)
        if classify is not None:
            slot.kind = cls._figure_kind(classify) or slot.kind

        # 3. Fold OCR text and the VLM description onto their slots.
        ocr = successful.get(EnrichmentKind.OCR)
        if ocr is not None:
            slot.ocr_text = ocr.text
        vlm = successful.get(EnrichmentKind.VLM)
        if vlm is not None:
            slot.description = vlm.text

        # 4. Fold a chart-to-data grid when it is a row-major list of rows.
        chart = successful.get(EnrichmentKind.CHART_TO_DATA)
        if chart is not None and isinstance(chart.data, list):
            slot.data_table = chart.data

        return slot

    @staticmethod
    def _figure_kind(classify: BlockEnrichment) -> FigureKind | None:
        """Best-effort read of the figure kind from a CLASSIFY enrichment's payload."""
        # 1. The kind may be recorded as the enrichment text or under a "kind" data key.
        raw = classify.text
        if isinstance(classify.data, dict):
            raw = classify.data.get("kind", raw)

        # 2. Coerce to a known FigureKind; an unrecognized value leaves the default in place.
        try:
            return FigureKind(raw) if raw is not None else None
        except ValueError:
            return None


__all__ = ["IRBundleAdapter"]
