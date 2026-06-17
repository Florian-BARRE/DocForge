# ====== Code Summary ======
# S1 — Parse stage: Docling → DocumentIR + figure crops → SeaweedFS.
# S1 operates on the PDF produced by S0 and never touches the original file again.
# Figure crops are uploaded as blobs; page screenshots are generated on-the-fly at request time.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from ir.models import BlockType, DocumentIR
from ir.serializer import MarkdownSerializer
from providers.parser import DoclingBackend
from storage.s3.client import S3Client

# ====== Local Project Imports ======
from .s0_ingest import S0Result


@dataclass(slots=True)
class S1Result:
    """
    Output artefacts produced by the S1 parsing stage.

    The IR is the canonical product; figure crop keys are stored in SeaweedFS and
    referenced in IR block provenance. Page screenshots are generated on-the-fly
    from the original PDF at request time — no page PNGs are stored.
    """

    ir: DocumentIR
    markdown_key: str                      # Object-store key for the faithful markdown view
    figure_crop_keys: dict[str, str]       # block_id → object-store key


class S1ParseStage(LoggerClass):
    """
    S1 — Parsing and rasterization stage.

    Responsibilities:
    1. Parse the PDF (from S0) into a DocumentIR using the configured parser backend.
    2. Render each PDF page as a PNG → upload to SeaweedFS.
    3. Crop each FIGURE block's bounding box → upload crop to SeaweedFS.
    4. Update the IR's figure blocks with their ``crop_key``.
    5. Serialize the IR to markdown → upload to SeaweedFS.

    What S1 does NOT do:
    - No OCR, no VLM, no figure classification (that is S2, P3).
    - No chunking or embedding (S4–S6, P4).
    - No Postgres writes (handled by the runner after this stage returns).
    """

    # Render resolution: 2× zoom for readable PNGs without oversized files
    _RENDER_DPI_ZOOM: float = 2.0

    def __init__(
        self,
        parser: DoclingBackend,
        s3: S3Client,
    ) -> None:
        """
        Initialize S1 with its dependencies.

        Args:
            parser (DoclingBackend): The parser backend to use.
            s3 (S3Client): SeaweedFS client for blob uploads.
        """
        LoggerClass.__init__(self)
        self._parser = parser
        self._s3 = s3
        self._md_serializer = MarkdownSerializer()

    async def run(self, s0: S0Result, fingerprint: str | None = None) -> S1Result:
        """
        Execute the S1 parse stage.

        Args:
            s0 (S0Result): Output from the S0 ingestion stage.
                ``s0.pdf_bytes`` must be populated (not None) before calling this method.
            fingerprint (str | None): P2 stage fingerprint used to build the markdown S3 key.
                When None (P1 fallback), a placeholder key suffix is used.

        Returns:
            S1Result: The DocumentIR, markdown key, and all uploaded blob keys.
        """
        self.logger.info(
            f"S1 started: doc_id={s0.doc_id} pages={s0.page_count}"
        )

        # 1. Parse PDF → DocumentIR (Docling runs in a thread pool inside the backend)
        ir = await self._parser.parse(
            pdf_bytes=s0.pdf_bytes,
            doc_id=s0.doc_id,
            source_hash=s0.source_hash,
        )

        # 2. Render and upload figure crops (page screenshots are generated on-the-fly)
        figure_crop_keys = await self._render_and_upload(s0, ir)

        # 3. Patch figure blocks in the IR with their crop_key from SeaweedFS
        ir = self._patch_figure_crop_keys(ir, figure_crop_keys)

        # 4. Serialize IR → faithful markdown → upload (uses fingerprint as key suffix in P2)
        markdown_key = await self._upload_markdown(s0, ir, fingerprint=fingerprint)

        result = S1Result(
            ir=ir,
            markdown_key=markdown_key,
            figure_crop_keys=figure_crop_keys,
        )

        self.logger.info(
            f"S1 done: doc_id={s0.doc_id} "
            f"blocks={len(ir.blocks)} "
            f"figures={len(figure_crop_keys)}"
        )
        return result

    # ─── Private helpers ───────────────────────────────────────────────────────

    async def _render_and_upload(
        self, s0: S0Result, ir: DocumentIR
    ) -> dict[str, str]:
        """
        Crop all figure bboxes from the PDF and upload them to SeaweedFS.

        Page screenshots are no longer pre-rendered here — they are generated
        on-the-fly from the original PDF at request time.

        Returns:
            dict[str, str]: block_id → object-store key for each uploaded figure crop.
        """
        loop = asyncio.get_event_loop()

        # 1. Crop synchronously in a thread pool (fitz is CPU-bound)
        figure_crops = await loop.run_in_executor(
            None,
            self._render_figure_crops_sync,
            s0.pdf_bytes,
            ir,
            s0.source_hash,
        )

        # 2. Upload figure crops concurrently
        await asyncio.gather(*[
            self._s3.upload(key=key, data=data, content_type="image/png")
            for _, key, data in figure_crops
        ])

        return {block_id: key for block_id, key, _ in figure_crops}

    def _render_figure_crops_sync(
        self,
        pdf_bytes: bytes,
        ir: DocumentIR,
        source_hash: str,
    ) -> list[tuple[str, str, bytes]]:
        """
        Synchronous figure crop rendering via PyMuPDF (runs in thread pool).

        Args:
            pdf_bytes (bytes): Raw PDF content.
            ir (DocumentIR): Parsed IR (provides figure block bboxes).
            source_hash (str): Content hash used to build S3 keys.

        Returns:
            list[tuple[str, str, bytes]]: (block_id, s3_key, png_bytes) per figure.
        """
        import fitz  # PyMuPDF

        figure_crops: list[tuple[str, str, bytes]] = []
        matrix = fitz.Matrix(self._RENDER_DPI_ZOOM, self._RENDER_DPI_ZOOM)

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for block in ir.figure_blocks:
                page_num = block.prov.page
                if page_num >= doc.page_count:
                    continue

                page = doc[page_num]
                page_w = page.rect.width
                page_h = page.rect.height

                # De-normalize bbox [0,1] → absolute coords; clamp to the page.
                x0, y0, x1, y1 = block.prov.bbox
                rx0, rx1 = sorted((x0 * page_w, x1 * page_w))
                ry0, ry1 = sorted((y0 * page_h, y1 * page_h))
                rect = fitz.Rect(rx0, ry0, rx1, ry1) & page.rect

                # Skip degenerate regions — a zero-area clip yields an unencodable pixmap.
                if rect.is_empty or rect.width < 2 or rect.height < 2:
                    self.logger.debug(f"S1: skipping degenerate figure crop for {block.id}")
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
                    crop_bytes = pix.tobytes("png")
                except Exception as exc:
                    # One bad bbox must never crash parsing — log and skip the crop.
                    self.logger.warning(f"S1: figure crop failed for {block.id}: {exc}")
                    continue

                key = S3Client.key_figure_crop(source_hash, block.id)
                figure_crops.append((block.id, key, crop_bytes))

        return figure_crops

    @staticmethod
    def _patch_figure_crop_keys(
        ir: DocumentIR, figure_crop_keys: dict[str, str]
    ) -> DocumentIR:
        """
        Return a new DocumentIR with figure blocks updated with their crop_key.

        Uses Pydantic model_copy for immutable update (IR is never mutated in-place).
        """
        updated_blocks = []
        for block in ir.blocks:
            if block.type == BlockType.FIGURE and block.figure is not None:
                crop_key = figure_crop_keys.get(block.id, "")
                updated_figure = block.figure.model_copy(update={"crop_key": crop_key})
                updated_block = block.model_copy(update={"figure": updated_figure})
                updated_blocks.append(updated_block)
            else:
                updated_blocks.append(block)

        return ir.model_copy(update={"blocks": updated_blocks})

    async def _upload_markdown(
        self, s0: S0Result, ir: DocumentIR, fingerprint: str | None = None
    ) -> str:
        """
        Serialize the IR to faithful markdown and upload to SeaweedFS.

        Args:
            s0 (S0Result): S0 output (provides source_hash for key construction).
            ir (DocumentIR): Parsed IR to serialize.
            fingerprint (str | None): P2 stage fingerprint.  If None, a placeholder
                is used (P1 backward-compat path).

        Returns:
            str: The S3 key where the markdown was stored.
        """
        markdown_text = self._md_serializer.serialize(ir)
        # Use real fingerprint in P2; fall back to placeholder in P1
        serialize_fp = fingerprint or "s1_no_fingerprint"
        key = S3Client.key_markdown(s0.source_hash, serialize_fp)

        await self._s3.upload(
            key=key,
            data=markdown_text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        self.logger.debug(f"Uploaded markdown → {key}")
        return key
