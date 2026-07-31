# ====== Code Summary ======
# Config of the Docling parser node — the Docling-specific PDF pipeline knobs the UI can set. OCR is
# ON by default: it is Docling's OWN in-process OCR (local, in-stack, no external API), so a scanned
# page or a photographed document yields real, searchable text out of the box — without it, an image
# document silently loses ALL its text. Docling only OCRs bitmap regions with no text layer, so a
# digital-born PDF/HTML (which already carries text) is untouched — the cost is paid only where it
# buys content. Table-structure recovery is ON for a richer IR, but the worker image must ship the
# Docling table model's native libs; turn it off here if that image is slimmed down.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class ParserDoclingConfig(NodeConfig):
    """Docling PDF pipeline options."""

    do_ocr: bool = Field(
        default=True,
        description="Let Docling run its own local OCR on bitmap pages/regions (no external API). "
        "ON by default so scans/photos/embedded images yield searchable text; a text-layer PDF is "
        "left untouched (Docling only OCRs where there is no extractable text). Turn off to skip "
        "OCR entirely on a text-only corpus.",
    )
    do_table_structure: bool = Field(
        default=True,
        description="Recover table cell structure (TableFormer). Needs the Docling table model's native libs.",
    )


__all__ = ["ParserDoclingConfig"]
