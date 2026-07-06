# ====== Code Summary ======
# Config of the Docling parser node — the Docling-specific PDF pipeline knobs the UI can set. OCR is
# OFF by default: DocForge delegates OCR to the enrich stage, not the parser. Table-structure
# recovery is ON for a richer IR, but the worker image must ship the Docling table model's native
# libs; turn it off here if that image is slimmed down.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class ParserDoclingConfig(NodeConfig):
    """Docling PDF pipeline options."""

    do_ocr: bool = Field(
        default=False,
        description="Let Docling run OCR itself. Off by default — OCR is delegated to the enrich stage.",
    )
    do_table_structure: bool = Field(
        default=True,
        description="Recover table cell structure (TableFormer). Needs the Docling table model's native libs.",
    )


__all__ = ["ParserDoclingConfig"]
