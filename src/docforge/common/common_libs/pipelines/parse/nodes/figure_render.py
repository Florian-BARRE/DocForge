# ====== Code Summary ======
# ParseFigureRender — the figure-crop node of the parse stage, running AFTER the parser escalation
# picked the winning IR. It downloads the PDF view, crops every FIGURE bbox (PyMuPDF, off the event
# loop), content-addresses each crop (sha256 of the PNG bytes) so bit-identical figures dedup to a
# single upload, uploads the unique crops, and patches each figure block's ``crop_key`` onto the IR.
# With no PDF view (a degraded run) it is a pure no-op. Ported from the v1 parse figure-render step;
# the only structural change is that it re-fetches the PDF by key (no separate fetch-pdf step).

# ====== Standard Library Imports ======
import asyncio
import hashlib
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines.core.ingest.stages.parse.helpers import ParseHelpers
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)
from common_libs.storage.s3.helpers import S3Helpers

# Render DPI zoom applied to each figure crop (2.0 = ~144 DPI at the PDF's default 72 DPI).
_RENDER_DPI_ZOOM: float = 2.0


class ParseFigureRenderInput(NodeInput):
    """Input of the figure-render node — the winning IR + the PDF view key (from the stage input)."""

    ir: Annotated[DocumentIR, FromNode("select", "ir")]
    pdf_key: Annotated[str | None, FromGroupInput()]


class ParseFigureRenderOutput(NodeOutput):
    """Output of the figure-render node — the patched IR + the block_id -> crop key map."""

    ir: DocumentIR
    figure_crop_keys: dict[str, str]


class ParseFigureRender(ActionNode):
    """Render + dedup + upload figure crops, then patch the IR with their object-store keys."""

    Input = ParseFigureRenderInput
    Output = ParseFigureRenderOutput

    async def execute(self, ctx: Context) -> ParseFigureRenderOutput:
        """
        Render + upload figure crops and patch the IR with their object-store keys.

        Args:
            ctx (Context): The resolved input (IR + pdf_key) + the object store service.

        Returns:
            ParseFigureRenderOutput: The patched IR + the block_id -> crop key map.
        """
        ir = ctx.input.ir

        # 1. Degraded run (no PDF view) -> nothing to render; pass the IR through unchanged.
        if ctx.input.pdf_key is None:
            return ParseFigureRenderOutput(ir=ir, figure_crop_keys={})

        # 2. Fetch the PDF view, then render the figure crops off the event loop (PyMuPDF is
        #    synchronous + CPU-bound).
        object_store = ctx.service("object_store")
        pdf_bytes = await object_store.download(ctx.input.pdf_key)
        loop = asyncio.get_event_loop()
        figure_crops = await loop.run_in_executor(
            None, self._render_figure_crops_sync, pdf_bytes, ir
        )

        # 3. Dedup: collapse identical (key -> bytes) pairs so a 27-slide deck sharing one header logo
        #    issues exactly ONE PutObject, not 27 (the crop key is sha256(crop_bytes)).
        unique_uploads: dict[str, bytes] = {}
        for _, key, data in figure_crops:
            unique_uploads.setdefault(key, data)
        await asyncio.gather(
            *[
                object_store.upload(key=key, data=data, content_type="image/png")
                for key, data in unique_uploads.items()
            ]
        )
        if (savings := len(figure_crops) - len(unique_uploads)) > 0:
            self.logger.info(
                f"Figure crop dedup saved {savings} object-store uploads "
                f"({len(figure_crops)} blocks -> {len(unique_uploads)} unique blobs)"
            )

        # 4. Patch each figure block's crop_key onto the IR + surface the block_id -> key map.
        figure_crop_keys = {block_id: key for block_id, key, _ in figure_crops}
        patched = ParseHelpers.patch_figure_crop_keys(ir, figure_crop_keys)
        return ParseFigureRenderOutput(ir=patched, figure_crop_keys=figure_crop_keys)

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


__all__ = ["ParseFigureRender", "ParseFigureRenderInput", "ParseFigureRenderOutput"]
