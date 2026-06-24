# ====== Code Summary ======
# DoclingBackend: converts a PDF to DocumentIR using Docling's document converter.
# Implements the ParserProvider Protocol: async parse() entry point delegates heavy
# Docling work to a thread pool to avoid blocking FastAPI's async event loop.
# Config id: "docling"

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from common_libs.providers.lang import LanguageDetector
from common_libs.providers.parser.base import ParserProvider

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR

# ====== Local Project Imports ======
from .ir_mapper import DoclingIRMapper


class DoclingBackend(ParserProvider, LoggerClass):
    """
    Docling-based parser implementing the ``ParserProvider`` Protocol.

    Config id: "docling"

    Docling provides:
    - Semantic block extraction with bounding boxes and reading order
    - Heading hierarchy detection
    - Table structure recognition (TableFormer, ~91% TEDS on FinTabNet ACCURATE mode)
    - Figure detection (bboxes)

    This adapter translates Docling's output to the canonical DocumentIR.
    Figure enrichment (OCR / VLM) is NOT done here — that belongs to S2 (P3).
    Page PNG rendering and figure crops are produced here as part of S1.

    GPU usage: controlled by ``use_gpu`` flag; DeviceManager makes the decision upstream.
    Heavy Docling calls run in a thread pool (``asyncio.get_event_loop().run_in_executor``)
    to avoid blocking FastAPI's async event loop.
    """

    name: str = "docling"
    version: str = "2"
    runs_on: str = "cpu"  # updated at runtime by DeviceManager via set_device()

    def __init__(self, use_gpu: bool = False) -> None:
        """
        Initialize the Docling backend.

        Args:
            use_gpu (bool): If True, Docling will attempt to use GPU for layout/table models.
        """
        LoggerClass.__init__(self)
        self._use_gpu = use_gpu
        self._converter = None  # Lazy initialization — loaded on first parse call
        self._lang_detector = LanguageDetector()  # offline language ID over the parsed text

    def set_device(self, runs_on: str) -> None:
        """
        Update the runs_on label (called by DeviceManager after detection).

        Args:
            runs_on (str): Device label, either ``"cpu"`` or ``"gpu"``.
        """
        self.runs_on = runs_on

    async def parse(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Parse PDF bytes into a DocumentIR using Docling.

        Heavy Docling work runs in a thread pool to not block the async event loop.

        Args:
            pdf_bytes (bytes): PDF content to parse.
            doc_id (str): Document UUID (written into the IR).
            source_hash (str): SHA-256 of the original file.

        Returns:
            DocumentIR: Fully populated IR with blocks, provenance, and language.
        """
        self.logger.info(f"Parsing document {doc_id} ({len(pdf_bytes)} bytes) with Docling…")

        # 1. Run Docling in a thread pool (CPU-bound, blocks the event loop otherwise)
        loop = asyncio.get_event_loop()
        ir = await loop.run_in_executor(
            None,
            self._parse_sync,
            pdf_bytes,
            doc_id,
            source_hash,
        )

        self.logger.info(
            f"Docling parsed {doc_id}: {ir.n_pages} pages, {len(ir.blocks)} blocks, "
            f"language={ir.language}"
        )
        return ir

    def _parse_sync(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        source_hash: str,
    ) -> DocumentIR:
        """
        Synchronous Docling parsing (runs inside a thread pool).

        Writes the PDF to a named temp file (Docling requires a file path),
        then converts and maps to DocumentIR via DoclingIRMapper.

        Args:
            pdf_bytes (bytes): Raw PDF content.
            doc_id (str): Document UUID string written into the IR.
            source_hash (str): SHA-256 hex of the original file.

        Returns:
            DocumentIR: Parsed canonical IR.
        """
        # 1. Lazy-load the Docling converter (heavy import — load once)
        converter = self._get_converter()

        # 2. Write PDF to a temp file (Docling works with file paths, not bytes)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)

        try:
            # 3. Run Docling conversion
            result = converter.convert(str(tmp_path))
            docling_doc = result.document

            # 4. Map Docling document → DocumentIR via the dedicated mapper
            return DoclingIRMapper.map_document(
                docling_doc=docling_doc,
                doc_id=doc_id,
                source_hash=source_hash,
                lang_detector=self._lang_detector,
            )

        finally:
            # 5. Always clean up the temp file
            tmp_path.unlink(missing_ok=True)

    def _get_converter(self) -> Any:
        """
        Lazy-load the Docling DocumentConverter (heavy — initializes ML models).

        Returns:
            Any: The Docling DocumentConverter instance (type imported lazily).

        Raises:
            RuntimeError: When the docling package is not installed.
        """
        if self._converter is None:
            try:
                from docling.datamodel.pipeline_options import PdfPipelineOptions  # type: ignore
                from docling.document_converter import (  # type: ignore
                    DocumentConverter,
                    PdfFormatOption,
                )

                # PdfPipelineOptions carries PDF-specific knobs (do_ocr, do_table_structure).
                # The old PipelineOptions no longer has these fields in docling >= 2.x.
                pipeline_opts = PdfPipelineOptions()
                # Disable OCR inside Docling — DocForge delegates that to S2 providers
                pipeline_opts.do_ocr = False
                # do_table_structure loads docling_ibm_models -> cv2 which requires libxcb.so.1
                # (X11 system lib absent in the slim runtime image). Disabled here; table
                # structure extraction can be re-enabled once libxcb1 is added to the image.
                pipeline_opts.do_table_structure = False

                self._converter = DocumentConverter(
                    format_options={"pdf": PdfFormatOption(pipeline_options=pipeline_opts)},
                )
                self.logger.info(f"Docling DocumentConverter initialized (gpu={self._use_gpu})")
            except ImportError as exc:
                raise RuntimeError(
                    f"docling is not installed. "
                    f"Run: uv add docling"
                ) from exc

        return self._converter
