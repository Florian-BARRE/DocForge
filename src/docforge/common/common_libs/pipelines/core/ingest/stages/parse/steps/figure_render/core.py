# ====== Code Summary ======
# IngestStageParseStepFigureRender — the third parse step. It crops every FIGURE bbox from the PDF
# bytes (PyMuPDF, run off the event loop), content-addresses each crop (sha256 of the PNG bytes) so
# bit-identical figures dedup to a single object-store upload, uploads the unique crops, and patches
# each figure block's ``crop_key`` onto the IR. A degraded run (no parse / no PDF) is a no-op. Ported
# from the former parse renderer's figure-crop path.

# ====== Standard Library Imports ======
import asyncio
import hashlib

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import NodeSpec, ServiceRef
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ...helpers import ParseHelpers
from ..base import IngestStageParseStepBase
from .context import IngestStageParseStepFigureRenderContext
from .errors import IngestStageParseStepFigureRenderError
from .io import (
    IngestStageParseStepFigureRenderInput,
    IngestStageParseStepFigureRenderOutput,
)

# Render DPI zoom applied to each figure crop (2.0 = ~144 DPI at the PDF's default 72 DPI).
_RENDER_DPI_ZOOM: float = 2.0


class IngestStageParseStepFigureRender(IngestStageParseStepBase):
    """
    Render figure crops, dedup + upload them, and patch the IR with their object-store keys.

    Reads the PDF bytes (fetch-pdf), the IR + degraded flag (parse); writes the patched IR and the
    block_id -> crop key map.
    """

    SPEC = NodeSpec(
        key="figure_render",
        name="Render figures",
        description=(
            "Crop each FIGURE bbox from the PDF view, content-address + dedup the crops, upload them "
            "to the object store, and patch each figure block with its crop key."
        ),
    )
    Input = IngestStageParseStepFigureRenderInput
    Output = IngestStageParseStepFigureRenderOutput
    Context = IngestStageParseStepFigureRenderContext
    Error = IngestStageParseStepFigureRenderError
    REQUIRES = (ServiceRef(name="object_store", description="Content-addressed blob store."),)

    async def execute(
        self, ctx: IngestStageParseStepFigureRenderContext
    ) -> IngestStageParseStepFigureRenderOutput:
        """
        Render + upload figure crops and patch the IR with their object-store keys.

        Args:
            ctx (IngestStageParseStepFigureRenderContext): Typed input + the object store.

        Returns:
            IngestStageParseStepFigureRenderOutput: The patched IR + the block_id -> crop key map.

        Raises:
            IngestStageParseStepFigureRenderError: When a crop upload fails.
        """
        ir = ctx.input.ir

        # 1. Degraded run (no parse / no PDF) -> nothing to render; pass the IR through unchanged.
        if ctx.input.degraded or ctx.input.pdf_bytes is None:
            return IngestStageParseStepFigureRenderOutput(ir=ir, figure_crop_keys={})

        # 2. Render the figure crops off the event loop (PyMuPDF is synchronous + CPU-bound).
        loop = asyncio.get_event_loop()
        figure_crops = await loop.run_in_executor(
            None, self._render_figure_crops_sync, ctx.input.pdf_bytes, ir
        )

        # 3. Dedup: collapse identical (key -> bytes) pairs so a 27-slide deck sharing one header logo
        # issues exactly ONE PutObject, not 27 (the crop key is sha256(crop_bytes)).
        unique_uploads: dict[str, bytes] = {}
        for _, key, data in figure_crops:
            unique_uploads.setdefault(key, data)

        try:
            await asyncio.gather(
                *[
                    ctx.object_store.upload(key=key, data=data, content_type="image/png")
                    for key, data in unique_uploads.items()
                ]
            )
        except Exception as exc:
            self.logger.error(f"Figure crop upload failed: {exc}")
            raise IngestStageParseStepFigureRenderError(
                f"Failed to upload {len(unique_uploads)} figure crop(s).",
                node_key=self.key,
                cause=exc,
            ) from exc

        if (savings := len(figure_crops) - len(unique_uploads)) > 0:
            self.logger.info(
                f"Figure crop dedup saved {savings} object-store uploads "
                f"({len(figure_crops)} blocks -> {len(unique_uploads)} unique blobs)"
            )

        # 4. Patch each figure block's crop_key onto the IR + surface the block_id -> key map.
        figure_crop_keys = {block_id: key for block_id, key, _ in figure_crops}
        patched = ParseHelpers.patch_figure_crop_keys(ir, figure_crop_keys)
        return IngestStageParseStepFigureRenderOutput(
            ir=patched, figure_crop_keys=figure_crop_keys
        )

    def _render_figure_crops_sync(
        self, pdf_bytes: bytes, ir: DocumentIR
    ) -> list[tuple[str, str, bytes]]:
        """
        Synchronously crop every figure bbox via PyMuPDF (runs in the executor thread pool).

        Each crop's object-store key is derived from ``sha256(crop_bytes)`` so two blocks whose pixel
        content is identical receive the same key and the upload step deduplicates them. Degenerate /
        failed crops are logged (never silent) and skipped.

        Args:
            pdf_bytes (bytes): Raw bytes of the PDF view.
            ir (DocumentIR): The IR whose figure blocks drive the crop rectangles.

        Returns:
            list[tuple[str, str, bytes]]: ``(block_id, crop_key, crop_png_bytes)`` per rendered crop.
        """
        import fitz  # PyMuPDF

        figure_crops: list[tuple[str, str, bytes]] = []
        matrix = fitz.Matrix(_RENDER_DPI_ZOOM, _RENDER_DPI_ZOOM)

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

                # Content-addressed: identical pixel bytes -> same object-store key.
                crop_hash = hashlib.sha256(crop_bytes).hexdigest()
                key = S3Helpers.key_figure_crop_by_hash(crop_hash)
                figure_crops.append((block.id, key, crop_bytes))

        return figure_crops


__all__ = ["IngestStageParseStepFigureRender"]
