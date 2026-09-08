# ====== Code Summary ======
# Pydantic response models for the sidecar's /parse contract. This is the SAME wire shape the
# paddle_server sidecar's /layout-parsing and /vl-parse routes emit (per-page reading-ordered blocks,
# tables as HTML, formulas as LaTeX, explicit per-page pixel dims) — that shared shape is the whole
# point: one DocForge IR mapper serves docling-sidecar parsers whatever the engine. The request body is
# raw PDF bytes (Content-Type: application/pdf), not a pydantic model (see router.py).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ParseBlockResponse(BaseModel):
    """
    One reading-order block within a page.

    Exactly one of `text` / `html` / `latex` is populated, selected by `label`:
    `table` -> `html` (the recognized table's HTML structure), `formula` -> `latex` (raw LaTeX
    source), everything else -> `text` (recognized text; empty for a plain `image`/`chart` block with
    no in-region text — the DocForge FigureRenderNode crops it from the bbox instead).

    Attributes:
        label (str): pp_structure-style layout label (e.g. "title", "paragraph_title", "text",
            "table", "formula", "image", "chart", "list", "caption") normalized from MinerU's `type` +
            `text_level`.
        bbox (list[int]): `[x0, y0, x1, y1]` in the page's pixel space (top-left origin) — the same
            space as `image_width`/`image_height` on the parent page (both are 1000: the normalized
            0–1000 basis MinerU's content_list uses, so the DocForge mapper's divide-by-dims yields
            [0, 1]).
        reading_order (int): 0-based position of this block within the page's block list.
        text (str | None): Recognized text — set for every label except table/formula.
        html (str | None): Recognized table HTML — set only for `label == "table"`.
        latex (str | None): Recognized formula LaTeX — set only for `label == "formula"`.
    """

    label: str = Field(..., description="pp_structure-style layout label normalized from MinerU.")
    bbox: list[int] = Field(..., description="[x0, y0, x1, y1] in the page's 0–1000 pixel space.")
    reading_order: int = Field(..., description="0-based position in this page's reading order.")
    text: str | None = Field(default=None, description="Recognized text (non table/formula).")
    html: str | None = Field(default=None, description="Recognized table HTML (label=='table').")
    latex: str | None = Field(
        default=None, description="Recognized formula LaTeX (label=='formula')."
    )


class ParsePageResponse(BaseModel):
    """
    One page's normalized parse result.

    Attributes:
        page_index (int): 0-based page index within the input PDF.
        image_width (int): Pixel width of the page's normalization space — the x divisor every block's
            `bbox` was measured against (always 1000: MinerU's normalized bbox basis).
        image_height (int): Pixel height of the page's normalization space (always 1000).
        blocks (list[ParseBlockResponse]): Reading-ordered blocks for this page.
    """

    page_index: int = Field(..., description="0-based page index within the input PDF.")
    image_width: int = Field(..., description="Page normalization width (the bbox x divisor).")
    image_height: int = Field(..., description="Page normalization height (the bbox y divisor).")
    blocks: list[ParseBlockResponse] = Field(..., description="Reading-ordered blocks.")


class ParseEngineResponse(BaseModel):
    """
    Engine/provenance metadata for a `POST /parse` response.

    Attributes:
        mineru (str): Installed `mineru` package version.
        pipeline (str): The MinerU model id that produced this response (MinerU2.5-Pro-2605-1.2B).
        backend (str): The MinerU VLM backend id used (e.g. "vlm-transformers").
    """

    mineru: str = Field(..., description="Installed mineru package version.")
    pipeline: str = Field(
        default="MinerU2.5-Pro-2605-1.2B",
        description="MinerU model id that produced this response.",
    )
    backend: str = Field(..., description="MinerU VLM backend id used for this parse.")


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
