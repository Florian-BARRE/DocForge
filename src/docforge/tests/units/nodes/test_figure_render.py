"""FigureRenderNode PDF-source selection: the canonical parser PDF is preferred (its bboxes align,
so figure crops are embedded), a view-only preview PDF (html/md parsed natively) is the fallback for
page renders ONLY (no crops, since its raster does not match the native-parse bboxes), and no PDF at
all passes the IR through untouched.

pypdfium2 is a worker-image native lib absent from the unit env, so the private rasterizer is
stubbed — these tests assert the SELECTION logic (which bytes, crops on/off), not the rasterization.
"""

from shared_libs.pipelines.ingest.nodes.parse.figure_render.core import (
    FigureRenderConfig,
    FigureRenderConsumes,
    FigureRenderNode,
)
from shared_libs.public_models import DocumentIR, IntakeResult, PageRender, PageRenders

_RENDER_ATTR = "_FigureRenderNode__render_sync"  # name-mangled private rasterizer


def _stub_render(captured: dict):
    """A rasterizer stub that records the (pdf_bytes, embed_crops) it was called with."""

    def render(_self, pdf_bytes: bytes, _ir: DocumentIR, embed_crops: bool) -> PageRenders:
        captured["pdf"] = pdf_bytes
        captured["embed_crops"] = embed_crops
        captured["calls"] = captured.get("calls", 0) + 1
        return PageRenders(pages=[PageRender(page_number=0, image=b"png", width=1, height=1)])

    return render


def _consumes(pdf_content: bytes | None, preview_pdf: bytes | None) -> FigureRenderConsumes:
    return FigureRenderConsumes(
        ingest=IntakeResult(
            source_hash="h", pdf_content=pdf_content, preview_pdf=preview_pdf, page_count=0
        ),
        ir=DocumentIR(doc_id="d", source_hash="h", n_pages=1, blocks=[]),
    )


async def test_preview_pdf_yields_page_renders_without_embedding_crops(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(FigureRenderNode, _RENDER_ATTR, _stub_render(captured))
    node = FigureRenderNode(id="r", config=FigureRenderConfig())

    out = await node.run(_consumes(pdf_content=None, preview_pdf=b"%PDF-preview"))

    assert out.pages.pages  # html/md now gets page renders (was empty before)
    assert captured["pdf"] == b"%PDF-preview"  # rendered from the preview channel
    assert captured["embed_crops"] is False  # crops NOT embedded against the mismatched raster


async def test_canonical_pdf_is_preferred_and_embeds_crops(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(FigureRenderNode, _RENDER_ATTR, _stub_render(captured))
    node = FigureRenderNode(id="r", config=FigureRenderConfig())

    # Even with a preview present, the canonical parser PDF wins (its bboxes align → crops embedded).
    out = await node.run(_consumes(pdf_content=b"%PDF-canonical", preview_pdf=b"%PDF-preview"))

    assert out.pages.pages
    assert captured["pdf"] == b"%PDF-canonical"
    assert captured["embed_crops"] is True


async def test_no_pdf_at_all_passes_the_ir_through_without_rendering(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(FigureRenderNode, _RENDER_ATTR, _stub_render(captured))
    node = FigureRenderNode(id="r", config=FigureRenderConfig())

    out = await node.run(_consumes(pdf_content=None, preview_pdf=None))

    assert out.pages.pages == []  # nothing to rasterize
    assert captured.get("calls", 0) == 0  # the rasterizer was never invoked
