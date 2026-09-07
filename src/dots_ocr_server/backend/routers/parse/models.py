# ====== Code Summary ======
# Pydantic response models for the sidecar's /parse contract. This is the SAME wire shape the
# mineru_server / paddle_server sidecars emit (per-page reading-ordered blocks, tables as HTML, formulas
# as LaTeX, explicit per-page pixel dims) — that shared shape is the whole point: one DocForge IR mapper
# family serves every docling-sidecar parser whatever the engine. The request body is raw PDF bytes
# (Content-Type: application/pdf), not a pydantic model (see router.py).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ParseBlockResponse(BaseModel):
    """
    One reading-order block within a page.

    Exactly one of `text` / `html` / `latex` is populated, selected by `label`:
    `Table` -> `html` (the recognized table's HTML structure), `Formula` -> `latex` (raw LaTeX
    source), everything else -> `text` (recognized text; omitted for a `Picture` block with no
    in-region text — the DocForge FigureRenderNode crops it from the bbox instead).

    Attributes:
        label (str): dots.ocr layout category (e.g. "Title", "Section-header", "Text", "List-item",
            "Table", "Formula", "Picture", "Caption", "Footnote", "Page-header", "Page-footer").
        bbox (list[int]): `[x0, y0, x1, y1]` in the RENDERED page image's PIXEL space (top-left
            origin) — the same space as `image_width`/`image_height` on the parent page. The DocForge
            mapper divides by those page dims to recover [0, 1].
        reading_order (int): 0-based position of this block within the page's block list.
        text (str | None): Recognized text — set for every label except Table/Formula/Picture.
        html (str | None): Recognized table HTML — set only for `label == "Table"`.
        latex (str | None): Recognized formula LaTeX — set only for `label == "Formula"`.
    """

    label: str = Field(..., description="dots.ocr layout category (its own taxonomy).")
    bbox: list[int] = Field(..., description="[x0, y0, x1, y1] in the rendered page's pixel space.")
    reading_order: int = Field(..., description="0-based position in this page's reading order.")
    text: str | None = Field(
        default=None, description="Recognized text (non Table/Formula/Picture)."
    )
    html: str | None = Field(default=None, description="Recognized table HTML (label=='Table').")
    latex: str | None = Field(
        default=None, description="Recognized formula LaTeX (label=='Formula')."
    )


class ParsePageResponse(BaseModel):
    """
    One page's normalized parse result.

    Attributes:
        page_index (int): 0-based page index within the input PDF.
        image_width (int): Pixel width of the RENDERED page image — the x divisor every block's `bbox`
            was measured against.
        image_height (int): Pixel height of the RENDERED page image (the y divisor).
        blocks (list[ParseBlockResponse]): Reading-ordered blocks for this page.
    """

    page_index: int = Field(..., description="0-based page index within the input PDF.")
    image_width: int = Field(..., description="Rendered page width in px (the bbox x divisor).")
    image_height: int = Field(..., description="Rendered page height in px (the bbox y divisor).")
    blocks: list[ParseBlockResponse] = Field(..., description="Reading-ordered blocks.")


class ParseEngineResponse(BaseModel):
    """
    Engine/provenance metadata for a `POST /parse` response.

    Attributes:
        dots_ocr (str): Installed vllm package version (the engine that ran dots.ocr).
        model (str): The dots.ocr model id/path that produced this response.
        backend (str): The inference backend id used ("vllm").
    """

    dots_ocr: str = Field(..., description="Installed vllm package version.")
    model: str = Field(..., description="dots.ocr model id/path that produced this response.")
    backend: str = Field(default="vllm", description="Inference backend id used for this parse.")


class ParseResponse(BaseModel):
    """
    Full response body of `POST /parse`.

    Attributes:
        pages (list[ParsePageResponse]): One entry per PDF page, in page order.
        n_pages (int): Number of pages parsed.
        engine (ParseEngineResponse): Provenance metadata.
    """

    pages: list[ParsePageResponse] = Field(..., description="One entry per PDF page.")
    n_pages: int = Field(..., description="Number of pages parsed.")
    engine: ParseEngineResponse = Field(..., description="Provenance metadata.")


__all__ = [
    "ParseBlockResponse",
    "ParsePageResponse",
    "ParseEngineResponse",
    "ParseResponse",
]
