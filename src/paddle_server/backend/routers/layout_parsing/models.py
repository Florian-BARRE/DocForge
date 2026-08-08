# ====== Code Summary ======
# Pydantic response models for POST /layout-parsing — the sidecar's OWN contract (not PaddleX's
# `paddlex --serve` basic-serving shape, see the research plan §B.4). Request body is raw PDF
# bytes (Content-Type: application/pdf), not a pydantic model — sub-pipeline toggles are query
# parameters instead (see router.py).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class LayoutBlockResponse(BaseModel):
    """
    One reading-order block within a page.

    Exactly one of `text` / `html` / `latex` is populated, selected by `label`:
    `table` -> `html` (the recognized table's HTML structure), `formula` -> `latex` (raw LaTeX
    source), everything else -> `text` (recognized/joined OCR text; empty for a plain `image`
    block with no in-region text — the DocForge FigureRenderNode crops it from the bbox instead).

    Attributes:
        label (str): PP-StructureV3 layout label (e.g. "doc_title", "paragraph_title", "text",
            "table", "formula", "image", "chart", "header", "footer", "seal", ...).
        bbox (list[int]): `[x1, y1, x2, y2]` in PIXELS, top-left origin — the same pixel space
            as `image_width`/`image_height` on the parent page.
        reading_order (int): 0-based position of this block within the page's block list, in
            reading order (PaddleX's own layout-ordering pass).
        text (str | None): Recognized/joined text — set for every label except table/formula.
        html (str | None): Recognized table HTML — set only for `label == "table"`.
        latex (str | None): Recognized formula LaTeX — set only for `label == "formula"`.
    """

    label: str = Field(..., description="PP-StructureV3 layout label.")
    bbox: list[int] = Field(..., description="[x1, y1, x2, y2] in pixels, top-left origin.")
    reading_order: int = Field(..., description="0-based position in this page's reading order.")
    text: str | None = Field(default=None, description="Recognized/joined text (non table/formula).")
    html: str | None = Field(default=None, description="Recognized table HTML (label=='table').")
    latex: str | None = Field(default=None, description="Recognized formula LaTeX (label=='formula').")


class LayoutPageResponse(BaseModel):
    """
    One page's normalized layout-parsing result.

    Attributes:
        page_index (int): 0-based page index within the input PDF.
        image_width (int): Pixel width of the rendered page image — the normalization divisor
            every block's `bbox` was measured against.
        image_height (int): Pixel height of the rendered page image.
        blocks (list[LayoutBlockResponse]): Reading-ordered blocks for this page.
    """

    page_index: int = Field(..., description="0-based page index within the input PDF.")
    image_width: int = Field(..., description="Rendered page-image pixel width.")
    image_height: int = Field(..., description="Rendered page-image pixel height.")
    blocks: list[LayoutBlockResponse] = Field(..., description="Reading-ordered blocks.")


class EngineInfoResponse(BaseModel):
    """
    Engine/provenance metadata for a `POST /layout-parsing` response.

    Attributes:
        paddleocr (str): Installed `paddleocr` package version.
        pipeline (str): Always "PP-StructureV3".
        sub_pipelines (dict): PaddleX's own `model_settings` — which optional sub-pipelines
            actually ran for this request (table/formula/seal/doc-preprocessor/...).
    """

    paddleocr: str = Field(..., description="Installed paddleocr package version.")
    pipeline: str = Field(default="PP-StructureV3", description="Always 'PP-StructureV3'.")
    sub_pipelines: dict = Field(..., description="Which optional sub-pipelines actually ran.")


class LayoutParsingResponse(BaseModel):
    """
    Full response body of `POST /layout-parsing`.

    Attributes:
        pages (list[LayoutPageResponse]): One entry per PDF page, in page order.
        n_pages (int): Number of pages parsed (== len(pages)).
        engine (EngineInfoResponse): Provenance metadata.
    """

    pages: list[LayoutPageResponse] = Field(..., description="One entry per PDF page.")
    n_pages: int = Field(..., description="Number of pages parsed.")
    engine: EngineInfoResponse = Field(..., description="Provenance metadata.")
