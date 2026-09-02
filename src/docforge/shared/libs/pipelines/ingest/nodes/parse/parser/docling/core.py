# ====== Code Summary ======
# The standard Docling parser node — the modular layout→OCR→TableFormer pipeline, first concrete child
# of BaseDoclingParserNode. It implements ONLY the two Docling-family seams: _build_converter (a
# PdfPipelineOptions DocumentConverter honouring the do_ocr / do_table_structure knobs) and _cache_key
# (those two axes). All parse plumbing (temp file, worker thread, locks), the IR mapping via
# DoclingIRMapper, scoring and the native/PDF degradation are inherited from the base.

# ====== Standard Library Imports ======
import threading
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..docling_base import BaseDoclingParserNode
from .config import ParserDoclingConfig


@NodeRegistry.register("parser")
class ParserDoclingNode(BaseDoclingParserNode):
    """
    Parse the PDF view with the Docling engine, mapping its output to the canonical IR.

    OCR and table-structure recovery are read from the Config; the IR quality score (computed by
    the base) drives escalation to the next parser when Docling extracts little text.
    """

    KIND = "docling"
    NAME = "Docling"
    SUMMARY = "Parse a PDF (or html/md natively) into the canonical IR with Docling."
    HOW_IT_WORKS = (
        "Runs Docling's DocumentConverter on the PDF view — or on the ORIGINAL html/md bytes, "
        "whose heading tree a PDF round-trip would flatten — in a worker thread (CPU-bound), and "
        "maps its blocks, tables, figures and provenance into the DocumentIR."
    )
    Config = ParserDoclingConfig
    UNIQUE_IN_GRAPH = True

    # Stage-cacheable (Phase-5 P1 flagship): a Docling parse is a pure, deterministic, LOCAL function
    # of the intake result + the OCR/table config axes — no network, no sampling — so a stored IR is
    # byte-identical to a re-parse. Only the standard Docling node opts in this slice; the Granite-VLM
    # and PP-Structure sidecar parsers are NOT cacheable here (VLM sampling / remote non-determinism).
    # Reviewer rule: bump CACHE_VERSION if the DoclingIRMapper output or the quality score changes.
    CACHEABLE = True
    CACHE_VERSION = "1"

    # Structured text formats Docling parses natively from the original bytes; the base reads the
    # matching temp-file suffix from _NATIVE_SUFFIX. Their heading tree survives intact, unlike a PDF
    # round-trip. The default converter already allows every InputFormat, so no OCR/table native libs
    # are needed for these — only the right suffix on the temp file.
    NATIVE_FORMATS = frozenset({"html", "md"})

    _PIPELINE = "standard"
    # Own converter cache + locks so the standard and VLM flavours never share a dict/lock.
    _converters: dict[tuple[Any, ...], Any] = {}
    _build_lock = threading.Lock()
    _convert_lock = threading.Lock()

    def _cache_key(self) -> tuple[Any, ...]:
        """Identify the converter by the two PdfPipelineOptions axes this node exposes."""
        config: ParserDoclingConfig = self.config
        return (config.do_ocr, config.do_table_structure)

    def _build_converter(self) -> Any:
        """Build the modular Docling DocumentConverter for this node's OCR/table options."""
        # 1. Lazy import — Docling pulls heavy native deps; only load them when a parse runs.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        config: ParserDoclingConfig = self.config
        # 2. Apply the OCR / table-structure knobs onto the standard PDF pipeline.
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = config.do_ocr
        pipeline_options.do_table_structure = config.do_table_structure
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )


__all__ = ["ParserDoclingNode"]
