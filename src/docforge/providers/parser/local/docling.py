# ====== Code Summary ======
# Docling parser backend: converts a PDF to DocumentIR using Docling's document converter.
# This adapter translates Docling's internal representation → the canonical IR schema.
# Docling is the default parser (ADR-2: wrap parsers, don't rewrite them).
# CPU and GPU are both supported; heavy work runs in a thread pool to avoid blocking the event loop.
# Config id: "docling"

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import io
import tempfile
import uuid
from pathlib import Path
from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
import fitz  # PyMuPDF — for page PNG rendering and raster detection
from loggerplusplus import LoggerClass
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
    TableData,
)
from providers.parser.base import ParserProvider
from providers.lang import LanguageDetector
from providers._registry import register


class DoclingBackend(ParserProvider, LoggerClass):
    """
    Docling-based parser implementing the ``ParserProvider`` Protocol.

    Config id: "docling"

    Docling provides:
    - Semantic block extraction with bounding boxes and reading order
    - Heading hierarchy detection
    - Table structure recognition (TableFormer, ~91% TEDS on FinTabNet ACCURATE mode)
    - Figure detection (bboxes)

    This adapter translates Docling's output to the canonical DocumentIR.
    Figure enrichment (OCR / VLM) is NOT done here — that belongs to S2 (P3).
    Page PNG rendering and figure crops are produced here as part of S1.

    GPU usage: controlled by ``use_gpu`` flag; DeviceManager makes the decision upstream.
    Heavy Docling calls run in a thread pool (``asyncio.get_event_loop().run_in_executor``)
    to avoid blocking FastAPI's async event loop.
    """

    name: str = "docling"
    version: str = "2"
    runs_on: str = "cpu"  # updated at runtime by DeviceManager via set_device()

    def __init__(self, use_gpu: bool = False) -> None:
        """
        Initialize the Docling backend.

        Args:
            use_gpu (bool): If True, Docling will attempt to use GPU for layout/table models.
        """
        LoggerClass.__init__(self)
        self._use_gpu = use_gpu
        self._converter = None  # Lazy initialization — loaded on first parse call
        self._lang_detector = LanguageDetector()  # offline language ID over the parsed text

    def set_device(self, runs_on: str) -> None:
        """
        Update the runs_on label (called by DeviceManager after detection).

        Args:
            runs_on (str): Device label, either ``"cpu"`` or ``"gpu"``.
        """
        self.runs_on = runs_on

    async def parse(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Parse PDF bytes into a DocumentIR using Docling.

        Heavy Docling work runs in a thread pool to not block the async event loop.

        Args:
            pdf_bytes (bytes): PDF content to parse.
            doc_id (str): Document UUID (written into the IR).
            source_hash (str): SHA-256 of the original file.

        Returns:
            DocumentIR: Fully populated IR with blocks, provenance, and language.
        """
        self.logger.info(f"Parsing document {doc_id} ({len(pdf_bytes)} bytes) with Docling…")

        # 1. Run Docling in a thread pool (CPU-bound, blocks the event loop otherwise)
        loop = asyncio.get_event_loop()
        ir = await loop.run_in_executor(
            None,
            self._parse_sync,
            pdf_bytes,
            doc_id,
            source_hash,
        )

        self.logger.info(
            f"Docling parsed {doc_id}: {ir.n_pages} pages, {len(ir.blocks)} blocks, "
            f"language={ir.language}"
        )
        return ir

    def _parse_sync(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Synchronous Docling parsing (runs inside a thread pool).

        Writes the PDF to a named temp file (Docling requires a file path),
        then converts and maps to DocumentIR.

        Args:
            pdf_bytes (bytes): Raw PDF content.
            doc_id (str): Document UUID string written into the IR.
            source_hash (str): SHA-256 hex of the original file.

        Returns:
            DocumentIR: Parsed canonical IR.
        """
        # 1. Lazy-load the Docling converter (heavy import — load once)
        converter = self._get_converter()

        # 2. Write PDF to a temp file (Docling works with file paths, not bytes)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)

        try:
            # 3. Run Docling conversion
            result = converter.convert(str(tmp_path))
            docling_doc = result.document

            # 4. Map Docling document → DocumentIR
            return self._map_to_ir(docling_doc, doc_id, source_hash)

        finally:
            # 5. Always clean up the temp file
            tmp_path.unlink(missing_ok=True)

    def _get_converter(self) -> Any:
        """
        Lazy-load the Docling DocumentConverter (heavy — initializes ML models).

        Returns:
            Any: The Docling DocumentConverter instance (type imported lazily).

        Raises:
            RuntimeError: When the docling package is not installed.
        """
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
                from docling.datamodel.pipeline_options import PdfPipelineOptions  # type: ignore

                # PdfPipelineOptions carries PDF-specific knobs (do_ocr, do_table_structure).
                # The old PipelineOptions no longer has these fields in docling ≥ 2.x.
                pipeline_opts = PdfPipelineOptions()
                # Disable OCR inside Docling — DocForge delegates that to S2 providers
                pipeline_opts.do_ocr = False
                # do_table_structure loads docling_ibm_models → cv2 which requires libxcb.so.1
                # (X11 system lib absent in the slim runtime image). Disabled here; table
                # structure extraction can be re-enabled once libxcb1 is added to the image.
                pipeline_opts.do_table_structure = False

                self._converter = DocumentConverter(
                    format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_opts)},
                )
                self.logger.info(f"Docling DocumentConverter initialized (gpu={self._use_gpu})")
            except ImportError as exc:
                raise RuntimeError(
                    f"docling is not installed. "
                    f"Run: uv add docling"
                ) from exc

        return self._converter

    def _map_to_ir(self, docling_doc: Any, doc_id: str, source_hash: str) -> DocumentIR:
        """
        Translate a Docling document object into a canonical DocumentIR.

        Docling's internal model exposes items with types, bboxes, and text.
        We map each item to the closest BlockType and populate Provenance.

        Args:
            docling_doc (Any): The Docling document object (type imported lazily).
            doc_id (str): Document UUID string.
            source_hash (str): SHA-256 hex of the original file.

        Returns:
            DocumentIR: Fully mapped canonical IR.
        """
        blocks: list[Block] = []
        reading_order = 0

        # 1. Count pages — num_pages is a method in docling ≥ 2.x, a plain int in older versions
        _np = getattr(docling_doc, "num_pages", 1)
        n_pages = (_np() if callable(_np) else _np) or 1

        # 2. Walk Docling items in reading order
        # iterate_items() returns (DocItem, int) tuples in docling ≥ 2.x
        for item, _depth in docling_doc.iterate_items():
            block = self._map_item(item, reading_order, docling_doc)
            if block is not None:
                blocks.append(block)
                reading_order += 1

        # 3. Detect language from the parsed text (reliable, offline); fall back to Docling's
        #    hint, then "und". Done after parsing so the detector sees the real document text.
        language = (
            self._lang_detector.detect(self._language_sample(blocks))
            or getattr(docling_doc, "language", None)
            or "und"
        )

        # 4. Quality estimate consumed by the S1 parse chain's gate.
        #    Heuristic: fraction of blocks that carry actual text content.  A scanned PDF
        #    parsed by Docling without OCR yields mostly figure blocks with no text — the
        #    ratio drops well below 0.5 and the chain can escalate to a heavier parser.
        text_blocks = sum(1 for b in blocks if (b.text or "").strip())
        quality_score = text_blocks / max(1, len(blocks)) if blocks else 0.0

        # 5. Assemble the DocumentIR
        return DocumentIR(
            doc_id=doc_id,
            source_hash=source_hash,
            n_pages=n_pages,
            language=language,
            blocks=blocks,
            quality_score=quality_score,
        )

    @staticmethod
    def _language_sample(blocks: list[Block], max_chars: int = 4000) -> str:
        """
        Concatenate text-bearing blocks (reading order) into a sample for language detection.

        Args:
            blocks (list[Block]): Parsed blocks.
            max_chars (int): Stop once this many characters are gathered (enough to detect).

        Returns:
            str: A text sample, possibly empty when the document carries no extractable text.
        """
        parts: list[str] = []
        total = 0
        for block in blocks:
            if not block.text:
                continue
            parts.append(block.text)
            total += len(block.text)
            if total >= max_chars:
                break
        return " ".join(parts)

    def _map_item(self, item: Any, reading_order: int, docling_doc: Any) -> Block | None:
        """
        Map a single Docling item to an IR Block.

        Args:
            item: A Docling DocItem (TextItem, TableItem, PictureItem, etc.).
            reading_order (int): Sequential index in the document.
            docling_doc: The parent DoclingDocument, used for page size lookup.

        Returns:
            Block | None: Mapped block, or None to skip this item.
        """
        # 1. Extract label string — docling ≥ 2.x uses a DocItemLabel enum
        raw_label = getattr(item, "label", None)
        if raw_label is None:
            return None
        label: str = raw_label.value if hasattr(raw_label, "value") else str(raw_label)

        # 2. Map label → BlockType (None means skip)
        block_type = self._label_to_block_type(label)
        if block_type is None:
            return None

        # 3. Extract provenance (page + normalized bbox)
        prov = self._extract_provenance(item, docling_doc)
        if prov is None:
            return None

        # 4. Generate a stable block ID from self_ref if available
        block_id = str(item.self_ref) if hasattr(item, "self_ref") and item.self_ref else str(uuid.uuid4())

        # 5. Extract type-specific content
        text: str | None = None
        table_data: TableData | None = None
        figure_data: FigureEnrichment | None = None
        level: int | None = None

        if block_type == BlockType.HEADING:
            text = self._get_text(item)
            # Docling exposes heading depth via item.level (int, 1-based)
            raw_level = getattr(item, "level", None)
            level = int(raw_level) if raw_level is not None else 1

        elif block_type == BlockType.TABLE:
            table_data = self._extract_table(item)

        elif block_type == BlockType.FIGURE:
            # Minimal figure placeholder — enrichment happens in S2 (P3)
            figure_data = FigureEnrichment(
                kind=FigureKind.PHOTO,
                crop_key="",
                relevance=1.0,
            )

        else:
            text = self._get_text(item)

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

    # ─── Docling label mapping ─────────────────────────────────────────────────

    _LABEL_MAP: dict[str, BlockType] = {
        "title": BlockType.HEADING,
        "section_header": BlockType.HEADING,
        "text": BlockType.PARAGRAPH,
        "paragraph": BlockType.PARAGRAPH,
        "list_item": BlockType.LIST_ITEM,
        "table": BlockType.TABLE,
        # Docling 2.x labels images "picture" (the old "figure" label is kept for safety).
        # Charts/figures are also surfaced as pictures and routed to S2 enrichment.
        "picture": BlockType.FIGURE,
        "figure": BlockType.FIGURE,
        "chart": BlockType.FIGURE,
        "caption": BlockType.CAPTION,
        "code": BlockType.CODE,
        "formula": BlockType.FORMULA,
        "page_header": BlockType.HEADER_FOOTER,
        "page_footer": BlockType.HEADER_FOOTER,
    }

    @classmethod
    def _label_to_block_type(cls, label: str) -> BlockType | None:
        """Map a Docling element label string to a BlockType, or None to skip."""
        return cls._LABEL_MAP.get(label.lower())

    # ─── Extraction helpers ────────────────────────────────────────────────────

    @staticmethod
    def _extract_provenance(item: Any, docling_doc: Any) -> Provenance | None:
        """
        Extract page and normalized bbox from a Docling item.

        Args:
            item: A Docling DocItem.
            docling_doc: The parent DoclingDocument (used to look up page size).

        Returns:
            Provenance | None: Normalized provenance, or None if unavailable.
        """
        try:
            prov_list = getattr(item, "prov", []) or []
            if not prov_list:
                return None

            prov_entry = prov_list[0]
            page_no = prov_entry.page_no          # 1-indexed in Docling
            page_idx = max(0, page_no - 1)        # 0-indexed for IR
            bbox = prov_entry.bbox

            # Resolve page dimensions from docling_doc.pages (dict keyed by 1-indexed page_no)
            page_obj = (docling_doc.pages or {}).get(page_no)
            page_size = getattr(page_obj, "size", None) if page_obj else None
            page_w = (getattr(page_size, "width", None) or 1.0) or 1.0
            page_h = (getattr(page_size, "height", None) or 1.0) or 1.0

            # Docling bboxes are often BOTTOM-LEFT origin (PDF convention): y grows upward,
            # so `t` (top edge) > `b` (bottom edge). Convert to TOP-LEFT screen coordinates
            # (y grows downward) so downstream rendering/cropping uses the right region.
            origin = getattr(bbox, "coord_origin", None)
            origin_str = getattr(origin, "value", str(origin)) if origin is not None else ""
            top, bottom = (bbox.t or 0.0), (bbox.b or 0.0)
            if "BOTTOM" in origin_str.upper():
                top_screen = page_h - top         # distance of top edge from the page top
                bottom_screen = page_h - bottom
            else:
                top_screen, bottom_screen = top, bottom

            # Normalize to [0, 1] with y0 < y1 (top-left convention)
            x0 = (bbox.l or 0.0) / page_w
            x1 = (bbox.r or page_w) / page_w
            y0 = top_screen / page_h
            y1 = bottom_screen / page_h
            x0, x1 = min(x0, x1), max(x0, x1)
            y0, y1 = min(y0, y1), max(y0, y1)

            return Provenance(page=page_idx, bbox=(x0, y0, x1, y1))

        except (AttributeError, IndexError, TypeError, ZeroDivisionError):
            return None

    @staticmethod
    def _get_text(item: Any) -> str | None:
        """Extract text content from a Docling item, preferring the exported markdown text."""
        # Try get_text() first (Docling 2.x API)
        if hasattr(item, "get_text"):
            try:
                return item.get_text() or None
            except Exception:
                pass
        # Fallback to text attribute
        return getattr(item, "text", None) or None

    @staticmethod
    def _extract_table(item: Any) -> TableData | None:
        """Extract structured table cells from a Docling TableItem."""
        try:
            # Docling TableItem exposes export_to_dataframe() or a grid attribute
            if hasattr(item, "data") and item.data:
                grid = item.data.grid
                if not grid:
                    return None
                cells = [
                    [str(cell.text or "") for cell in row]
                    for row in grid
                ]
                n_rows = len(cells)
                n_cols = max(len(r) for r in cells) if cells else 0
                return TableData(
                    cells=cells,
                    n_rows=n_rows,
                    n_cols=n_cols,
                    has_header=n_rows > 1,
                )
        except (AttributeError, TypeError):
            pass
        return None


# ─── Config ──────────────────────────────────────────────────────────────────


def _flatten_provider_spec(v: Any) -> Any:
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


@register("parser")
class DoclingConfig(BaseModel):
    """
    Configuration for the Docling PDF parser backend.

    Config id: "docling" — structural block extraction, table recognition, figure detection.

    Attributes:
        id: Provider discriminator — always "docling".
        use_gpu: Use GPU acceleration for Docling layout models when True.
    """

    _label: ClassVar[str] = "Docling — structural parser with table + figure detection"
    _category: ClassVar[str] = "parser"

    id: Literal["docling"] = "docling"
    use_gpu: bool = Field(default=False, description="Use GPU for Docling layout models.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> "DoclingBackend":
        """Instantiate DoclingBackend from this config."""
        return DoclingBackend(use_gpu=self.use_gpu)

    def merge_defaults(self, cfg: Any) -> "DoclingConfig":
        """Merge deployment env defaults."""
        return self.model_copy(update={
            "use_gpu": self.use_gpu or getattr(cfg, "DOCLING_USE_GPU", False),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Docling is always available — bundled in the container."""
        return True, "Default structural parser"
