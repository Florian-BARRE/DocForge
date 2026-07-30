# ====== Code Summary ======
# FigureRenderNode — COMPLETES the IR at the end of the parse stage: rasterizes the PDF pages
# and embeds each FIGURE block's cropped image into the IR itself (Block.figure.crop), so the IR
# leaves parse "ultra complet" — every figure carries its bytes, ready for the enrich stage to
# classify/OCR/describe per block. Also emits the page renders (highlight-on-page UI; the worker
# stores them as blobs). pypdfium2 is lazy-imported (native lib, worker image); the CPU-bound
# rendering runs off the event loop. Degrades to a pass-through when there is no PDF view.

# ====== Standard Library Imports ======
import asyncio
import io

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import (
    DocumentIR,
    FigureEnrichment,
    IntakeResult,
    PageRender,
    PageRenders,
)


class FigureRenderConfig(NodeConfig):
    """Rasterization knobs."""

    scale: float = Field(
        default=2.0, gt=0, description="Rasterization scale (1.0 ≈ 72 dpi; 2.0 ≈ 144 dpi)."
    )
    render_pages: bool = Field(
        default=True,
        description="Keep the full-page renders (highlight-on-page); crops are always embedded.",
    )


class FigureRenderConsumes(NodeInput):
    """The PDF view (via the ingest result) and the parsed IR locating the figures."""

    ingest: IntakeResult = Field(
        description="The intake output (the PDF the pages are rendered from)."
    )
    ir: DocumentIR = Field(description="The parsed IR whose figure crops are to be embedded.")


class FigureRenderProduces(NodeOutput):
    """The COMPLETED IR (crops embedded) and the page renders."""

    ir: DocumentIR = Field(description="The COMPLETE IR — every figure now carries its crop bytes.")
    pages: PageRenders = Field(description="Full-page renders (UI previews, stored as blobs).")


@NodeRegistry.register("render")
class FigureRenderNode(ActionNode):
    """Embed each figure's cropped image into the IR and emit the page renders."""

    KIND = "figure_render"
    UNIQUE_IN_GRAPH = True
    NAME = "Figure renderer"
    SUMMARY = "Complete the IR: embed each figure block's cropped image (+ page renders)."
    HOW_IT_WORKS = (
        "Renders every page with pypdfium2 at the configured scale, crops each FIGURE block's "
        "normalized bbox out of its page image and embeds the PNG bytes into the block "
        "(Block.figure.crop). The IR leaves parse complete; the page renders feed the "
        "highlight-on-page UI."
    )
    Config = FigureRenderConfig

    Consumes = FigureRenderConsumes
    Produces = FigureRenderProduces

    def __render_sync(self, pdf_bytes: bytes, ir: DocumentIR) -> PageRenders:
        """Synchronous rendering (worker thread): rasterize pages, embed crops into the IR."""
        # 1. Lazy import — pypdfium2 is a native lib shipped in the worker image only.
        import pypdfium2 as pdfium

        config: FigureRenderConfig = self.config
        document = pdfium.PdfDocument(pdf_bytes)
        try:
            # 2. Group figures by their page so each page's crops happen while that page's image is
            #    alive, then the image is dropped before the next — peak PIL RAM is O(1 page), not
            #    O(all pages) (a 100-page A4 doc at 144 dpi is ~600 MB if all held at once).
            figs_by_page: dict[int, list] = {}
            for block in ir.figure_blocks:
                figs_by_page.setdefault(block.provenance.page, []).append(block)

            # 3. Stream page by page: rasterize → (optionally) emit its render → crop its figures →
            #    let the PIL image fall out of scope so the GC can reclaim it before the next page.
            renders: list[PageRender] = []
            for index in range(len(document)):
                image = document[index].render(scale=config.scale).to_pil()
                if config.render_pages:
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    renders.append(
                        PageRender(
                            page_number=index,
                            image=buffer.getvalue(),
                            width=image.width,
                            height=image.height,
                        )
                    )
                for block in figs_by_page.get(index, ()):
                    x0, y0, x1, y1 = block.provenance.bbox
                    box = (
                        int(x0 * image.width),
                        int(y0 * image.height),
                        int(x1 * image.width),
                        int(y1 * image.height),
                    )
                    # A degenerate bbox (zero area) has nothing to crop.
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue
                    buffer = io.BytesIO()
                    image.crop(box).save(buffer, format="PNG")
                    if block.figure is None:
                        block.figure = FigureEnrichment()
                    block.figure.crop = buffer.getvalue()
            return PageRenders(pages=renders)
        finally:
            document.close()

    async def run(self, data: FigureRenderConsumes) -> FigureRenderProduces:
        """Render off the event loop; pass the IR through untouched without a PDF view."""
        # 1. No PDF → nothing to rasterize (a non-convertible source); the IR passes through.
        if data.ingest.pdf_content is None:
            self.logger.warning(f"No PDF view to render; IR passes through without crops")
            return FigureRenderProduces(ir=data.ir, pages=PageRenders())

        # 2. CPU-bound rendering runs in a worker thread; crops are embedded into the IR.
        pages = await asyncio.to_thread(self.__render_sync, data.ingest.pdf_content, data.ir)
        embedded = sum(1 for block in data.ir.figure_blocks if block.figure and block.figure.crop)
        self.logger.debug(f"Rendered {len(pages.pages)} pages, embedded {embedded} figure crops")
        return FigureRenderProduces(ir=data.ir, pages=pages)


__all__ = ["FigureRenderNode", "FigureRenderConfig"]
