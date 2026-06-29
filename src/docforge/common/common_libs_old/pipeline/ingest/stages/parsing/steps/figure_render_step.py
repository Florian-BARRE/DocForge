# ====== Code Summary ======
# FigureRenderStep — the second parse step. It crops every FIGURE bbox from the derived PDF
# (PyMuPDF, run off the event loop), content-addresses each crop (sha256 of the PNG bytes) so
# bit-identical figures dedup to a single object-store upload, uploads the unique crops, and patches
# each figure block's ``crop_key`` onto the IR. The per-figure crop keys are threaded onto the parse
# scratch for the markdown step. Ported from the former s1 renderer's figure-crop path.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..helpers import ParseHelpers
from ..scratch import PARSE_SCRATCH_KEY

if TYPE_CHECKING:
    from common_libs.domain.ir.models import DocumentIR
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.storage.s3.client import S3Client


class FigureRenderStep(IngestStep):
    """
    Native parse step — renders figure crops, dedups + uploads them, and patches the IR.

    Reads ``ingest_result`` (PDF bytes), ``ir``, and the parse scratch; writes the patched ``ir``
    (figure blocks gain their ``crop_key``) and fills ``scratch.figure_crop_keys``.
    """

    KEY: ClassVar[str] = "figure_render"
    NAME: ClassVar[str] = "Render figures"
    DESCRIPTION: ClassVar[str] = (
        "Crop each FIGURE bbox from the derived PDF, content-address + dedup the crops, upload them "
        "to the object store, and patch each figure block with its crop key."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ingest_result", "ir", PARSE_SCRATCH_KEY)
    PRODUCES: ClassVar[tuple[str, ...]] = ("ir", PARSE_SCRATCH_KEY)

    # Render DPI zoom applied to each figure crop (2.0 = ~144 DPI at the PDF's default 72 DPI).
    _RENDER_DPI_ZOOM: ClassVar[float] = 2.0

    def __init__(self, s3: "S3Client") -> None:
        """
        Wire the step around the object-store client.

        Args:
            s3 (S3Client): SeaweedFS S3-compatible client for the figure-crop uploads.
        """
        IngestStep.__init__(self)
        self._s3 = s3

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Render + upload figure crops and patch the IR with their object-store keys.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Render the figure crops off the event loop (PyMuPDF is synchronous + CPU-bound).
        ir = ctx.ir
        loop = asyncio.get_event_loop()
        figure_crops = await loop.run_in_executor(
            None,
            self._render_figure_crops_sync,
            ctx.ingest_result.pdf_bytes,
            ir,
        )

        # 2. Dedup: collapse identical (key → bytes) pairs so a 27-slide deck sharing one header logo
        # issues exactly ONE PutObject, not 27 (the crop key is sha256(crop_bytes)).
        unique_uploads: dict[str, bytes] = {}
        for _, key, data in figure_crops:
            unique_uploads.setdefault(key, data)

        await asyncio.gather(*[
            self._s3.upload(key=key, data=data, content_type="image/png")
            for key, data in unique_uploads.items()
        ])

        if (savings := len(figure_crops) - len(unique_uploads)) > 0:
            self.logger.info(
                f"Figure crop dedup saved {savings} object-store uploads "
                f"({len(figure_crops)} blocks → {len(unique_uploads)} unique blobs)"
            )

        # 3. Patch each figure block's crop_key onto the IR + thread the keys onto the scratch.
        figure_crop_keys = {block_id: key for block_id, key, _ in figure_crops}
        ctx.ir = ParseHelpers.patch_figure_crop_keys(ir, figure_crop_keys)
        ctx.aux[PARSE_SCRATCH_KEY].figure_crop_keys = figure_crop_keys

    def _render_figure_crops_sync(
        self,
        pdf_bytes: bytes,
        ir: "DocumentIR",
    ) -> list[tuple[str, str, bytes]]:
        """
        Synchronously crop every figure bbox via PyMuPDF (runs in the executor thread pool).

        Each crop's object-store key is derived from ``sha256(crop_bytes)`` so two blocks whose
        pixel content is identical receive the same key and the upload step deduplicates them.
        Degenerate / failed crops are logged (never silent) and skipped.

        Args:
            pdf_bytes (bytes): Raw bytes of the derived PDF.
            ir (DocumentIR): The IR whose figure blocks drive the crop rectangles.

        Returns:
            list[tuple[str, str, bytes]]: ``(block_id, crop_key, crop_png_bytes)`` per rendered crop.
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
                    self.logger.debug(f"Skipping degenerate figure crop for {block.id}")
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
                    crop_bytes = pix.tobytes("png")
                except Exception as exc:
                    self.logger.warning(f"Figure crop failed for {block.id}: {exc}")
                    continue

                # Content-addressed: identical pixel bytes → same object-store key.
                crop_hash = hashlib.sha256(crop_bytes).hexdigest()
                key = S3Helpers.key_figure_crop_by_hash(crop_hash)
                figure_crops.append((block.id, key, crop_bytes))

        return figure_crops


__all__ = ["FigureRenderStep"]
