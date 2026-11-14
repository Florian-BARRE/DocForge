# ====== Code Summary ======
# SidecarIRMapper — the abstract sidecar-response → canonical DocumentIR adapter shared by the four
# sidecar parsers (dots_ocr, mineru, paddleocr_vl, pp_structure). Every sidecar emits the SAME per-page
# block contract (`{pages:[{page_index, image_width, image_height, blocks:[{label, bbox, reading_order,
# text|html|latex}]}], n_pages}`), so the whole skeleton lives here: walk pages in order, order each
# page's blocks by their reading_order, resolve the label to a BlockType (skipping unmapped ones), fill
# the one content slot the type needs (text | table | figure | formula-latex), normalize the pixel bbox
# against the rendered page dims, then build the heading tree. An engine subclass declares ONLY what
# differs: its LABEL_MAP, its HEADING_LEVELS and its log label. Pure module — no engine import, so it
# maps a canned response in a unit test without a live sidecar.

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
from .geometry import SidecarGeometry
from .table import SidecarTableFlattener


class SidecarIRMapper:
    """Static adapter mapping a sidecar response into the canonical DocumentIR.

    Subclasses set ``LABEL_MAP`` (lowercased sidecar label → BlockType; unmapped labels are skipped),
    ``HEADING_LEVELS`` (heading label → absolute level; unknown heading labels default to 2),
    ``LOG_LABEL`` (the engine's name in the debug line) and their own ``logger``.
    """

    logger = loggerplusplus.bind(identifier="SidecarIRMapper")

    # Lowercased sidecar label → canonical BlockType. Labels absent from the map are skipped.
    LABEL_MAP: dict[str, BlockType] = {}
    # Lowercased heading label → absolute level. The sidecars distinguish few heading depths, so the
    # tree is often flat below level 2 (an accepted limitation — it only costs breadcrumb depth).
    HEADING_LEVELS: dict[str, int] = {}
    # Level of a heading whose label is not in HEADING_LEVELS (a section).
    DEFAULT_HEADING_LEVEL = 2
    # The engine's name in the debug line (e.g. "MinerU").
    LOG_LABEL = "sidecar"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @classmethod
    def _map_block(
        cls,
        raw: dict[str, Any],
        page_index: int,
        block_index: int,
        doc_id: str,
        dims: tuple[float, float],
    ) -> Block | None:
        """Map one sidecar block dict to an IR Block, or None to skip an unmapped label."""
        # 1. Resolve the label → BlockType, or skip the block entirely (unmapped labels).
        label = str(raw.get("label", "")).strip().lower()
        block_type = cls.LABEL_MAP.get(label)
        if block_type is None:
            return None

        # 2. Normalize the pixel bbox against the RENDERED page-image dims (top-left origin, no
        #    y-flip). The sidecar returns the actual page-image width/height it rendered.
        image_width, image_height = dims
        provenance = SidecarGeometry.make_provenance(
            raw.get("bbox"), page_index, image_width, image_height
        )

        # 3. Fill the one content slot the type needs.
        text: str | None = None
        table: TableData | None = None
        figure: FigureEnrichment | None = None
        level: int | None = None
        if block_type == BlockType.HEADING:
            text = raw.get("text") or None
            level = cls.HEADING_LEVELS.get(label, cls.DEFAULT_HEADING_LEVEL)
        elif block_type == BlockType.TABLE:
            table = SidecarTableFlattener.html_to_table(raw.get("html"))
        elif block_type == BlockType.FORMULA:
            # The LaTeX source rides in the text slot — chunking treats a formula as text.
            text = raw.get("latex") or raw.get("text") or None
        elif block_type == BlockType.FIGURE:
            # Empty slot: figure_render fills the crop from the normalized bbox; enrich refines kind.
            figure = FigureEnrichment()
        else:
            text = raw.get("text") or None

        # 4. Namespace the id by doc_id + page + a monotonic block index (the global counter set in
        #    map_response, NOT the sidecar's own reading_order, which is untrusted and may repeat
        #    within a page and collide) → the id is globally unique and stable across re-parses.
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
        Translate a sidecar response into a canonical DocumentIR.

        Args:
            response (dict[str, Any]): The sidecar JSON: ``pages`` (each with image dims + blocks),
                and ``n_pages``.
            doc_id (str): Document identifier written into the IR.
            source_hash (str): Content-addressing hash of the original bytes.

        Returns:
            DocumentIR: The mapped IR (its quality score is computed by the parser base).
        """
        pages = response.get("pages") or []

        # 1. Walk pages in order; within a page, order blocks by their reading_order. The IR's
        #    reading_order is a global counter across pages (page-major), like every other parser.
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
                block = cls._map_block(raw, page_index, len(blocks), doc_id, dims)
                if block is not None:
                    block.reading_order = len(blocks)
                    blocks.append(block)

        # 2. Build the heading tree (parent_id) — breadcrumbs and section chunking walk it later.
        BaseParserHelpers.assign_heading_tree(blocks)

        # 3. Language is left UNSET here (""): the dedicated docmeta/language node owns detection
        #    downstream (parser-agnostic, per-collection configurable), so no parser hint leaks in.
        n_pages = int(response.get("n_pages") or len(pages) or 0)
        cls.logger.debug(f"{cls.LOG_LABEL}→IR: {doc_id} → {n_pages} pages, {len(blocks)} blocks")
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=n_pages,
            blocks=blocks,
        )


__all__ = ["SidecarIRMapper"]
