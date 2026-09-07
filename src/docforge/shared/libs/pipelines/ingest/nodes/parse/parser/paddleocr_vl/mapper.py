# ====== Code Summary ======
# Translates a PaddleOCR-VL 1.6 sidecar response into the canonical DocumentIR — the paddleocr_vl→IR
# adapter. The PaddleOCR-VL sidecar (src/paddle_server, POST /vl-parse) emits the SAME clean per-page
# block contract the PP-StructureV3 sidecar does (`{pages:[{page_index, image_width, image_height,
# blocks:[{label, bbox, reading_order, text|html|latex}]}], n_pages}`) — that shared shape is
# deliberate, so this mapper reuses PpStructureParseHelpers (label→BlockType, heading level, bbox
# normalization) and PpStructureTableFlattener (the span-aware HTML→grid flattener) rather than
# duplicating them. Only the class identity differs (a distinct brick in the palette / trace); the
# per-block logic is the shared contract logic. Pure module — no engine import, so it maps a canned
# response in a unit test without a live sidecar.

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
from ..pp_structure.helpers import PpStructureParseHelpers


class PaddleOcrVlIRMapper:
    """Static adapter mapping a PaddleOCR-VL 1.6 sidecar response into the canonical DocumentIR.

    Consumes the SAME sidecar contract as PpStructureIRMapper and reuses its helpers/flattener; kept a
    distinct class so paddleocr_vl is its own brick in the palette and execution trace.
    """

    logger = loggerplusplus.bind(identifier="PaddleOcrVlIRMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PaddleOcrVlIRMapper is a static-only class and cannot be instantiated.")

    @classmethod
    def __map_block(
        cls,
        raw: dict[str, Any],
        page_index: int,
        block_index: int,
        doc_id: str,
        dims: tuple[float, float],
    ) -> Block | None:
        """Map one sidecar block dict to an IR Block, or None to skip an unmapped label."""
        # 1. Resolve the label → BlockType, or skip the block entirely (unmapped: seal, footnote,
        #    aside_text — PaddleOCR-VL's own markdown_ignore_labels are treated the same way).
        label = str(raw.get("label", "")).strip()
        block_type = PpStructureParseHelpers.label_to_block_type(label)
        if block_type is None:
            return None

        # 2. Normalize the pixel bbox against the page-image dims (top-left origin, no y-flip).
        image_width, image_height = dims
        provenance = PpStructureParseHelpers.make_provenance(
            raw.get("bbox"), page_index, image_width, image_height
        )

        # 3. Fill the one content slot the type needs.
        text: str | None = None
        table: TableData | None = None
        figure: FigureEnrichment | None = None
        level: int | None = None
        if block_type == BlockType.HEADING:
            text = raw.get("text") or None
            level = PpStructureParseHelpers.heading_level(label)
        elif block_type == BlockType.TABLE:
            table = PpStructureParseHelpers.html_to_table(raw.get("html"))
        elif block_type == BlockType.FORMULA:
            # The LaTeX source rides in the text slot — chunking treats a formula as text.
            text = raw.get("latex") or raw.get("text") or None
        elif block_type == BlockType.FIGURE:
            # Empty slot: figure_render fills the crop from the normalized bbox; enrich refines kind.
            figure = FigureEnrichment()
        else:
            text = raw.get("text") or None

        # 4. Namespace the id by doc_id + page + a monotonic block index (the global counter set in
        #    map_response), so the id is globally unique and stable across re-parses.
        block_id = f"{doc_id}:p{page_index}:b{block_index}"
        return Block(
            id=block_id,
            block_type=block_type,
            provenance=provenance,
            reading_order=0,  # replaced by the global counter in map_response
            level=level,
            text=text,
            table=table,
            figure=figure,
        )

    @classmethod
    def map_response(cls, response: dict[str, Any], doc_id: str, source_hash: str) -> DocumentIR:
        """
        Translate a PaddleOCR-VL 1.6 sidecar response into a canonical DocumentIR.

        Args:
            response (dict[str, Any]): The sidecar JSON: ``pages`` (each with image dims + blocks),
                and ``n_pages``.
            doc_id (str): Document identifier written into the IR.
            source_hash (str): Content-addressing hash of the original bytes.

        Returns:
            DocumentIR: The mapped IR (its quality score is computed by the parser base).
        """
        pages = response.get("pages") or []

        # 1. Walk pages in order; within a page, order blocks by their reading_order (the sidecar
        #    assigns it from parsing_res_list's already-visual order). The IR's reading_order is a
        #    global counter across pages (page-major), like every other parser mapper.
        blocks: list[Block] = []
        for page in pages:
            page_index = int(page.get("page_index", 0))
            dims = (float(page.get("image_width") or 0.0), float(page.get("image_height") or 0.0))
            raw_blocks = sorted(
                page.get("blocks") or [], key=lambda item: item.get("reading_order", 0)
            )
            for raw in raw_blocks:
                # The global counter (len(blocks)) is BOTH the block's IR reading_order and the id's
                # index component, so the id can never collide on a repeated sidecar reading_order.
                block = cls.__map_block(raw, page_index, len(blocks), doc_id, dims)
                if block is not None:
                    block.reading_order = len(blocks)
                    blocks.append(block)

        # 2. Build the heading tree (parent_id) — breadcrumbs and section chunking walk it later.
        BaseParserHelpers.assign_heading_tree(blocks)

        # 3. Language is left UNSET here (""): the dedicated docmeta/language node owns detection
        #    downstream (parser-agnostic, per-collection configurable), so no parser hint leaks in.
        n_pages = int(response.get("n_pages") or len(pages) or 0)
        cls.logger.debug(f"PaddleOCR-VL→IR: {doc_id} → {n_pages} pages, {len(blocks)} blocks")
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=n_pages,
            blocks=blocks,
        )


__all__ = ["PaddleOcrVlIRMapper"]
