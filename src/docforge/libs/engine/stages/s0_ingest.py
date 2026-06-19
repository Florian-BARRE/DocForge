# ====== Code Summary ======
# S0 — Ingestion stage: content-address the original file (sha256), convert office formats
# to PDF via Gotenberg, detect the native/raster fork, upload artifacts to SeaweedFS.
# S0 is the entry gate: it never touches an ML model and must stay cheap and fast.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.converter import (
    GOTENBERG_FORMATS,
    NATIVE_PDF_FORMATS,
    GotenbergConverter,
)
from libs.data.storage.s3.client import S3Client
from libs.data.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .s0_helpers import S0IngestHelpers


@dataclass(slots=True)
class S0Result:
    """
    Output artefacts produced by the S0 ingestion stage.

    All downstream stages (S1…) receive this object instead of raw bytes.
    """

    doc_id: str
    source_hash: str            # SHA-256 hex of original bytes (content-address key)
    original_key: str           # Object-store key: originals/{source_hash}
    # pdf_bytes is None when S0Result is restored from the P2 node cache.
    # The engine downloads the PDF from S3 (pdf_key) before invoking S1 if needed.
    pdf_bytes: bytes | None     # PDF for S1 parsing; None = lazy (load from pdf_key)
    pdf_key: str                # Object-store key: derived/{source_hash}/pdf
    page_count: int             # Total page count
    original_filename: str
    original_format: str        # File extension (lowercase, no dot)
    file_size: int              # Original file size in bytes
    needs_ocr: bool             # True when at least one page was detected as raster
    implicit_meta: dict[str, Any] = field(default_factory=dict)


class S0IngestStage(LoggerClass):
    """
    S0 — Ingestion and conversion stage.

    Responsibilities:
    1. Compute SHA-256 of the original file → content-address.
    2. Upload the original to SeaweedFS at ``originals/{sha256}``.
    3. Convert office formats (docx, pptx, xlsx…) → PDF via Gotenberg.
       PDF files are passed through unchanged.
       Spreadsheets (xlsx/csv): Gotenberg conversion produces the display PDF;
       native parsing (structured cells) is handled in S1 regardless.
    4. Upload the PDF to SeaweedFS at ``derived/{sha256}/pdf``.
    5. Perform the native/raster fork (PyMuPDF page text check) → sets ``needs_ocr``.
    6. Extract file-intrinsic implicit metadata (filename, extension, size, source_hash).

    What S0 does NOT do:
    - No ML calls (no OCR, no layout models, no VLM).
    - No parsing into blocks (that is S1).
    - No database writes (the caller / runner manages DB transactions).
    """

    def __init__(
        self,
        s3: S3Client,
        converter: GotenbergConverter,
    ) -> None:
        """
        Initialize S0 with its dependencies.

        Args:
            s3 (S3Client): SeaweedFS S3-compatible client for artifact upload.
            converter (GotenbergConverter): Gotenberg client for office → PDF conversion.
        """
        LoggerClass.__init__(self)
        self._s3 = s3
        self._converter = converter

    async def run(
        self,
        file_bytes: bytes,
        filename: str,
        doc_id: str | None = None,
    ) -> S0Result:
        """
        Execute the S0 ingestion stage.

        Args:
            file_bytes (bytes): Raw uploaded file bytes.
            filename (str): Original filename (extension determines the conversion path).
            doc_id (str | None): Optional pre-assigned document UUID; generated if None.

        Returns:
            S0Result: All S0 output artefacts, ready for S1.
        """
        # 1. Assign document ID
        effective_doc_id = doc_id or str(uuid.uuid4())

        # 2. Content-address the original (SHA-256)
        source_hash = S0IngestHelpers.sha256(file_bytes)
        original_format = S0IngestHelpers.extract_extension(filename)

        self.logger.info(
            f"S0 started: doc_id={effective_doc_id} filename={filename!r} "
            f"format={original_format} size={len(file_bytes)} bytes sha256={source_hash[:12]}…"
        )

        # 3. Upload original to SeaweedFS
        original_key = S3Helpers.key_original(source_hash)
        await self._s3.upload(
            key=original_key,
            data=file_bytes,
            content_type=S0IngestHelpers.mime_type(original_format),
        )
        self.logger.debug(f"Uploaded original → {original_key}")

        # 4. Obtain PDF bytes
        if original_format in NATIVE_PDF_FORMATS:
            # Already a PDF — pass through
            pdf_bytes = file_bytes
            page_count = S0IngestHelpers.count_pages_fast(pdf_bytes)
        elif original_format in GOTENBERG_FORMATS:
            # Office format → Gotenberg conversion
            convert_result = await self._converter.convert(file_bytes, filename)
            pdf_bytes = convert_result.pdf_bytes
            page_count = convert_result.page_count
        else:
            # Unknown format: store as-is, attempt to treat as PDF
            # (fallback coverage — Tika/Extractous is P3+)
            self.logger.warning(
                f"Unknown format {original_format!r} — attempting direct PDF passthrough."
            )
            pdf_bytes = file_bytes
            page_count = S0IngestHelpers.count_pages_fast(pdf_bytes)

        # 5. Upload PDF to SeaweedFS
        pdf_key = S3Helpers.key_pdf(source_hash)
        await self._s3.upload(
            key=pdf_key,
            data=pdf_bytes,
            content_type="application/pdf",
        )
        self.logger.debug(f"Uploaded PDF → {pdf_key} ({page_count} pages)")

        # 6. Native / raster fork: detect if any page requires OCR
        needs_ocr = S0IngestHelpers.detect_raster_pages(pdf_bytes)
        if needs_ocr:
            self.logger.info(f"Raster pages detected in {filename!r} → OCR will be needed (S2).")

        # 7. Build implicit metadata from file-intrinsic properties
        implicit_meta = S0IngestHelpers.build_implicit_meta(
            filename=filename,
            original_format=original_format,
            file_size=len(file_bytes),
            source_hash=source_hash,
            page_count=page_count,
            needs_ocr=needs_ocr,
        )

        result = S0Result(
            doc_id=effective_doc_id,
            source_hash=source_hash,
            original_key=original_key,
            pdf_bytes=pdf_bytes,
            pdf_key=pdf_key,
            page_count=page_count,
            original_filename=filename,
            original_format=original_format,
            file_size=len(file_bytes),
            needs_ocr=needs_ocr,
            implicit_meta=implicit_meta,
        )

        self.logger.info(
            f"S0 done: doc_id={effective_doc_id} pages={page_count} needs_ocr={needs_ocr}"
        )
        return result
