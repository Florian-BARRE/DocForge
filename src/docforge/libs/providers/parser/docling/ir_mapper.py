# ====== Code Summary ======
# Translates a parsed Docling document object into the canonical DocumentIR.
# Walks Docling items in reading order, maps each element to the closest BlockType,
# and populates Blocks with provenance, text, table, or figure data.
#
# Label mapping and language/quality helpers are extracted to quality_helpers.py
# (DoclingQualityHelpers) to keep this file under 200 lines.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from libs.providers.lang import LanguageDetector

# ====== Internal Project Imports ======
from libs.domain.ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    TableData,
)

# ====== Local Project Imports ======
from .extraction_helpers import DoclingExtractionHelpers
from .quality_helpers import DoclingQualityHelpers


class DoclingIRMapper:
    """
    Maps a parsed Docling document object to the canonical DocumentIR.

    Responsibilities:
    - Walk Docling items in reading order.
    - Map Docling element labels → BlockType (delegated to DoclingQualityHelpers).
    - Delegate provenance and table extraction to DoclingExtractionHelpers.
    - Detect document language and compute quality score.
    """

    logger = loggerplusplus.bind(identifier="DoclingIRMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a static-only mapper class."""
        raise TypeError("DoclingIRMapper is a static-only class and cannot be instantiated.")

    @classmethod
    def map_document(
        cls,
        docling_doc: Any,
        doc_id: str,
        source_hash: str,
        lang_detector: LanguageDetector,
    ) -> DocumentIR:
        """
        Translate a Docling document object into a canonical DocumentIR.

        Args:
            docling_doc (Any): The Docling document object (type imported lazily).
            doc_id (str): Document UUID string.
            source_hash (str): SHA-256 hex of the original file.
            lang_detector (LanguageDetector): Offline language detector instance.

        Returns:
            DocumentIR: Fully mapped canonical IR.
        """
        blocks: list[Block] = []
        reading_order = 0

        # 1. Count pages — num_pages is a method in docling >= 2.x, a plain int in older versions
        _np = getattr(docling_doc, "num_pages", 1)
        n_pages = (_np() if callable(_np) else _np) or 1

        # 2. Walk Docling items in reading order
        # iterate_items() returns (DocItem, int) tuples in docling >= 2.x
        for item, _depth in docling_doc.iterate_items():
            block = cls._map_item(item, reading_order, docling_doc, doc_id)
            if block is not None:
                blocks.append(block)
                reading_order += 1

        # 3. Detect language from the parsed text (reliable, offline); fall back to Docling's
        #    hint, then "und". Done after parsing so the detector sees the real document text.
        language = (
            lang_detector.detect(DoclingQualityHelpers.language_sample(blocks))
            or getattr(docling_doc, "language", None)
            or "und"
        )

        # 4. Quality estimate consumed by the S1 parse chain's gate.
        #    Heuristic: fraction of blocks that carry actual text content.  A scanned PDF
        #    parsed by Docling without OCR yields mostly figure blocks with no text — the
        #    ratio drops well below 0.5 and the chain can escalate to a heavier parser.
        text_blocks = sum(1 for b in blocks if (b.text or "").strip())
        quality_score = text_blocks / max(1, len(blocks)) if blocks else 0.0

        cls.logger.debug(
            f"DoclingIRMapper: {doc_id} -> {n_pages} pages, {len(blocks)} blocks, "
            f"lang={language}, quality={quality_score:.2f}"
        )

        # 5. Assemble the DocumentIR
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=n_pages,
            language=language,
            blocks=blocks,
            quality_score=quality_score,
        )

    @classmethod
    def _map_item(cls, item: Any, reading_order: int, docling_doc: Any, doc_id: str) -> Block | None:
        """
        Map a single Docling item to an IR Block.

        Args:
            item: A Docling DocItem (TextItem, TableItem, PictureItem, etc.).
            reading_order (int): Sequential index in the document.
            docling_doc: The parent DoclingDocument, used for page size lookup.
            doc_id (str): Owning document UUID — namespaces the block id (see step 4).

        Returns:
            Block | None: Mapped block, or None to skip this item.
        """
        # 1. Extract label string — docling >= 2.x uses a DocItemLabel enum
        raw_label = getattr(item, "label", None)
        if raw_label is None:
            return None
        label: str = raw_label.value if hasattr(raw_label, "value") else str(raw_label)

        # 2. Map label → BlockType (None means skip)
        block_type = DoclingQualityHelpers.label_to_block_type(label)
        if block_type is None:
            return None

        # 3. Extract provenance (page + normalized bbox)
        prov = DoclingExtractionHelpers.extract_provenance(item, docling_doc)
        if prov is None:
            return None

        # 4. Generate a block ID. Docling's self_ref (e.g. "#/texts/0") is only unique
        #    WITHIN a document, but the block table's primary key is the id alone — so it
        #    must be namespaced by doc_id, otherwise a second document re-using "#/texts/0"
        #    collides on block_pkey. doc_id + self_ref is globally unique and stable.
        raw_ref = (
            str(item.self_ref)
            if hasattr(item, "self_ref") and item.self_ref
            else str(uuid.uuid4())
        )
        block_id = f"{doc_id}:{raw_ref}"

        # 5. Extract type-specific content
        text: str | None = None
        table_data: TableData | None = None
        figure_data: FigureEnrichment | None = None
        level: int | None = None

        if block_type == BlockType.HEADING:
            text = DoclingExtractionHelpers.get_text(item)
            # Docling exposes heading depth via item.level (int, 1-based)
            raw_level = getattr(item, "level", None)
            level = int(raw_level) if raw_level is not None else 1

        elif block_type == BlockType.TABLE:
            table_data = DoclingExtractionHelpers.extract_table(item)

        elif block_type == BlockType.FIGURE:
            # Minimal figure placeholder — enrichment happens in S2 (P3)
            figure_data = FigureEnrichment(
                kind=FigureKind.PHOTO,
                crop_key="",
                relevance=1.0,
            )

        else:
            text = DoclingExtractionHelpers.get_text(item)

        # 6. Build the Block
        return Block(
            id=block_id,
            type=block_type,
            prov=prov,
            reading_order=reading_order,
            level=level,
            text=text,
            table=table_data,
            figure=figure_data,
        )
