# ====== Code Summary ======
# Translates a parsed Docling document into the canonical DocumentIR — the docling→IR adapter. It
# walks Docling items in reading order, maps each label to a BlockType, and fills each Block with
# provenance / text / table / figure via DoclingParseHelpers. Docling items are typed as Any, so
# this module loads without docling installed; only a real parse needs the package. The parse
# QUALITY SCORE is NOT computed here — the parser base derives it from the returned IR.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    TableData,
)

# ====== Local Project Imports ======
from ..base import BaseParserHelpers
from .helpers import DoclingParseHelpers


class DoclingIRMapper:
    """Static adapter mapping a Docling document into the canonical DocumentIR."""

    logger = loggerplusplus.bind(identifier="DoclingIRMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DoclingIRMapper is a static-only class and cannot be instantiated.")

    @classmethod
    def __map_item(
        cls, item: Any, reading_order: int, docling_doc: Any, doc_id: str
    ) -> Block | None:
        """Map a single Docling item to an IR Block, or None to skip it."""
        # 1. Resolve the label (docling 2.x uses a DocItemLabel enum) → BlockType, or skip.
        raw_label = getattr(item, "label", None)
        if raw_label is None:
            return None
        label = raw_label.value if hasattr(raw_label, "value") else str(raw_label)
        block_type = DoclingParseHelpers.label_to_block_type(label)
        if block_type is None:
            return None

        # 2. Provenance is mandatory — an item we cannot place is dropped.
        provenance = DoclingParseHelpers.extract_provenance(item, docling_doc)
        if provenance is None:
            return None

        # 3. Namespace the block id by doc_id: Docling's self_ref (e.g. "#/texts/0") is only unique
        #    within a document, so doc_id + self_ref stays globally unique and stable.
        raw_ref = str(item.self_ref) if getattr(item, "self_ref", None) else f"item/{reading_order}"
        block_id = f"{doc_id}:{raw_ref}"

        # 4. Fill the one content slot the type needs.
        text: str | None = None
        table: TableData | None = None
        figure: FigureEnrichment | None = None
        level: int | None = None
        if block_type == BlockType.HEADING:
            text = DoclingParseHelpers.get_text(item)
            raw_level = getattr(item, "level", None)
            level = int(raw_level) if raw_level is not None else 1
        elif block_type == BlockType.TABLE:
            table = DoclingParseHelpers.extract_table(item)
        elif block_type == BlockType.FIGURE:
            # Empty slot: figure_render fills the crop; classify (enrich) refines the kind.
            figure = FigureEnrichment()
        else:
            text = DoclingParseHelpers.get_text(item)

        return Block(
            id=block_id,
            block_type=block_type,
            provenance=provenance,
            reading_order=reading_order,
            level=level,
            text=text,
            table=table,
            figure=figure,
        )

    @classmethod
    def map_document(cls, docling_doc: Any, doc_id: str, source_hash: str) -> DocumentIR:
        """
        Translate a Docling document into a canonical DocumentIR.

        Args:
            docling_doc (Any): The parsed Docling document object.
            doc_id (str): Document identifier written into the IR.
            source_hash (str): Content-addressing hash of the original bytes.

        Returns:
            DocumentIR: The mapped IR (its quality score is computed by the parser base).
        """
        # 1. Page count — num_pages is a method in docling >= 2.x, an int in older versions.
        raw_n_pages = getattr(docling_doc, "num_pages", 1)
        n_pages = (raw_n_pages() if callable(raw_n_pages) else raw_n_pages) or 1

        # 2. Walk Docling items in reading order, mapping each to a Block.
        blocks: list[Block] = []
        for item, _depth in docling_doc.iterate_items():
            block = cls.__map_item(item, len(blocks), docling_doc, doc_id)
            if block is not None:
                blocks.append(block)

        # 3. Build the heading tree (parent_id) — breadcrumbs and section chunking walk it later.
        BaseParserHelpers.assign_heading_tree(blocks)

        # 4. Language: Docling's hint for now (an offline detector can refine it later).
        language = getattr(docling_doc, "language", "") or ""

        cls.logger.debug(
            f"Docling→IR: {doc_id} → {n_pages} pages, {len(blocks)} blocks, lang={language!r}"
        )
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=n_pages,
            language=language,
            blocks=blocks,
        )


__all__ = ["DoclingIRMapper"]
