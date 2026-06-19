# ====== Code Summary ======
# S1Renderer — figure-crop rendering + markdown serialization/upload for the S1 parse stage.
# Owns the S3 client, the markdown serializer, and the render DPI zoom.  Extracted from
# S1ParseStage so the stage focuses on driving the parser chain and stamping IR lineage.
# These methods are instance-bound (they emit self.logger debug/info/warning) so they live
# in a small composed class rather than a static helper.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.data.storage.s3.client import S3Client

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.models import DocumentIR
from libs.core.ir.serializer import MarkdownSerializer
from libs.data.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .s0_ingest import S0Result


class S1Renderer(LoggerClass):
    """
    Renders figure crops and serialises markdown for the S1 parse stage.

    Crops are content-addressed (``sha256(crop_bytes)``) so bit-identical figures dedup to a
    single S3 upload.  The markdown serializer renders the IR to faithful markdown that is
    uploaded under a fingerprint-derived key.
    """

    _RENDER_DPI_ZOOM: float = 2.0

    def __init__(self, s3: S3Client) -> None:
        """
        Initialise the renderer with its dependencies.

        Args:
            s3 (S3Client): SeaweedFS client for blob uploads.
        """
        LoggerClass.__init__(self)
        self._s3 = s3
        self._md_serializer = MarkdownSerializer()

    async def render_and_upload(
        self, s0: S0Result, ir: DocumentIR
    ) -> dict[str, str]:
        """
        Crop all figure bboxes from the PDF and upload them to SeaweedFS.

        Crops are stored under a **content-addressed** key
        (``figures/by-hash/<sha256[:2]>/<sha256>.png``) so a logo or page header
        repeating across every slide of a deck only uploads — and only ever
        stores — a single PNG.  Multiple block IDs map to the same crop_key
        when their pixel bytes are bit-identical, which also gives the S2
        provider-call cache 100% hit-rate on those repeated figures.

        Returns:
            dict[str, str]: block_id → object-store key for each figure crop.
                Multiple block_ids can share the same key after dedup.
        """
        loop = asyncio.get_event_loop()
        figure_crops = await loop.run_in_executor(
            None,
            self._render_figure_crops_sync,
            s0.pdf_bytes,
            ir,
        )

        # Dedup: collapse identical (key → bytes) pairs so a 27-slide deck with
        # the same header logo issues exactly ONE PutObject, not 27.
        unique_uploads: dict[str, bytes] = {}
        for _, key, data in figure_crops:
            unique_uploads.setdefault(key, data)

        await asyncio.gather(*[
            self._s3.upload(key=key, data=data, content_type="image/png")
            for key, data in unique_uploads.items()
        ])

        if (savings := len(figure_crops) - len(unique_uploads)) > 0:
            self.logger.info(
                f"S1: figure crop dedup saved {savings} S3 uploads "
                f"({len(figure_crops)} blocks → {len(unique_uploads)} unique blobs)"
            )

        return {block_id: key for block_id, key, _ in figure_crops}

    def _render_figure_crops_sync(
        self,
        pdf_bytes: bytes,
        ir: DocumentIR,
    ) -> list[tuple[str, str, bytes]]:
        """Synchronous figure crop rendering via PyMuPDF (runs in thread pool).

        Each crop's S3 key is derived from ``sha256(crop_bytes)`` so two blocks
        whose pixel content is identical receive the same key and the upload
        step deduplicates them.
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

                x0, y0, x1, y1 = block.prov.bbox
                rx0, rx1 = sorted((x0 * page_w, x1 * page_w))
                ry0, ry1 = sorted((y0 * page_h, y1 * page_h))
                rect = fitz.Rect(rx0, ry0, rx1, ry1) & page.rect

                if rect.is_empty or rect.width < 2 or rect.height < 2:
                    self.logger.debug(f"S1: skipping degenerate figure crop for {block.id}")
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
                    crop_bytes = pix.tobytes("png")
                except Exception as exc:
                    self.logger.warning(f"S1: figure crop failed for {block.id}: {exc}")
                    continue

                # Content-addressed: identical pixel bytes → same S3 key.
                crop_hash = hashlib.sha256(crop_bytes).hexdigest()
                key = S3Helpers.key_figure_crop_by_hash(crop_hash)
                figure_crops.append((block.id, key, crop_bytes))

        return figure_crops

    async def upload_markdown(
        self, s0: S0Result, ir: DocumentIR, fingerprint: str | None = None
    ) -> str:
        """Serialise the IR to faithful markdown and upload to SeaweedFS."""
        markdown_text = self._md_serializer.serialize(ir)
        serialize_fp = fingerprint or "s1_no_fingerprint"
        key = S3Helpers.key_markdown(s0.source_hash, serialize_fp)
        await self._s3.upload(
            key=key,
            data=markdown_text.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        )
        self.logger.debug(f"Uploaded markdown → {key}")
        return key


# ------------------- Public API ------------------- #
__all__ = ["S1Renderer"]
