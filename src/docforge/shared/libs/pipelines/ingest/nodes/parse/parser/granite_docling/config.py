# ====== Code Summary ======
# Config of the Granite-Docling VLM parser node. The VLM pipeline reads rendered page images and
# predicts DocTags with a single 258M vision-language model, so it has NONE of the modular pipeline's
# do_ocr / do_table_structure knobs (those are PdfPipelineOptions axes). Its real axes: the PINNED
# model revision (a reproducible HF fetch — a retagged main cannot silently change parse output),
# whether to trust the PDF's own text layer over the VLM prediction, and the per-page token budget.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig

# Default: ibm-granite/granite-docling-258M `main` at 2025-09-23. Pinned so runtime downloads are
# reproducible across worker rebuilds and independent of a moving HF branch tag.
_DEFAULT_REVISION = "982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe"


class ParserGraniteDoclingConfig(NodeConfig):
    """Granite-Docling VLM pipeline options."""

    revision: str = Field(
        default=_DEFAULT_REVISION,
        description="Pinned ibm-granite/granite-docling-258M git revision (main @ 2025-09-23) so the "
        "runtime HuggingFace download is reproducible and a retagged main cannot silently change "
        "parse output. Override per collection to track a newer model.",
    )
    force_backend_text: bool = Field(
        default=False,
        description="Trust the PDF's own text layer instead of the VLM-predicted text where a text "
        "layer exists. Off by default so the VLM reads every page (the point of the VLM pipeline).",
    )
    max_new_tokens: int = Field(
        default=4096,
        description="Upper bound on the DocTags tokens the VLM generates per page. Higher captures "
        "denser pages at more latency; 4096 is the granite default.",
    )


__all__ = ["ParserGraniteDoclingConfig"]
