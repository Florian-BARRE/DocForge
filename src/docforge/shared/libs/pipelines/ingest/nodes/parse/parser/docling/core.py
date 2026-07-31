# ====== Code Summary ======
# The Docling parser node — the first concrete child of BaseParserNode. It implements ONLY _parse:
# lazy-imports docling (heavy native models, so the module loads without it), resolves a PROCESS-
# WIDE cached DocumentConverter for its options (building one loads the layout/table models — tens
# of seconds — so it happens once per option set, not per document), runs the CPU-bound conversion
# in a worker thread under a lock (convert() is not documented thread-safe), and maps the result to
# the canonical IR via DoclingIRMapper. I/O, scoring and degradation all live in the base.

# ====== Standard Library Imports ======
import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from ..base import BaseParserNode
from .config import ParserDoclingConfig
from .mapper import DoclingIRMapper


@NodeRegistry.register("parser")
class ParserDoclingNode(BaseParserNode):
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

    # Structured text formats Docling parses natively from the original bytes → temp-file suffix
    # (Docling picks its backend from the extension). Their heading tree survives intact, unlike a
    # PDF round-trip. The default converter already allows every InputFormat, so no OCR/table native
    # libs are needed for these — only the right suffix on the temp file.
    NATIVE_FORMATS = frozenset({"html", "md"})
    _NATIVE_SUFFIX: dict[str, str] = {"html": ".html", "md": ".md"}

    # Process-wide converter CACHE, keyed by the option set: constructing a DocumentConverter
    # loads Docling's layout/table models (tens of seconds), so each option set is built once and
    # reused by every node instance in the worker. convert() is not documented thread-safe, so a
    # single lock serializes conversions. This is a cache of live resources — never config/state.
    _converters: dict[tuple[bool, bool], Any] = {}
    _build_lock = threading.Lock()
    _convert_lock = threading.Lock()

    def __converter(self) -> Any:
        """Resolve the process-shared DocumentConverter for this node's options (build once)."""
        # 1. Lazy import — Docling pulls heavy native deps; only load them when a parse runs.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        config: ParserDoclingConfig = self.config
        key = (config.do_ocr, config.do_table_structure)
        # 2. Build the converter once per option set (double-checked under the build lock).
        with self._build_lock:
            if key not in self._converters:
                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = config.do_ocr
                pipeline_options.do_table_structure = config.do_table_structure
                self._converters[key] = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                    }
                )
                self.logger.info(f"Docling converter built for options {key}")
        return self._converters[key]

    def __parse_sync(self, content: bytes, suffix: str, source_hash: str) -> DocumentIR:
        """Synchronous Docling parse (runs in a worker thread): convert the bytes, map to the IR."""
        # 1. Resolve the shared converter (built once per option set).
        converter = self.__converter()

        # 2. Docling needs a file path and picks its backend from the extension — write the bytes to
        #    a temp file with the format's suffix, convert, always clean up.
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            # 3. Serialize conversions — the shared converter is not documented thread-safe.
            with self._convert_lock:
                result = converter.convert(str(tmp_path))
            return DoclingIRMapper.map_document(
                result.document, doc_id=source_hash, source_hash=source_hash
            )
        finally:
            # 4. A leftover temp file is harmless; Windows may still hold the handle briefly.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning(f"Could not remove temp file {tmp_path}; leaving it behind")

    async def _parse(self, source: IntakeResult) -> DocumentIR:
        """Run the CPU-bound Docling conversion off the event loop and map it to the IR.

        Parses the PDF view when one exists; otherwise the ORIGINAL html/md bytes natively (their
        heading tree survives, where a PDF round-trip would flatten it).
        """
        if source.pdf_content is not None:
            content, suffix = source.pdf_content, ".pdf"
        else:
            content = source.source_content or b""
            suffix = self._NATIVE_SUFFIX[source.source_format]
        return await asyncio.to_thread(self.__parse_sync, content, suffix, source.source_hash)


__all__ = ["ParserDoclingNode"]
