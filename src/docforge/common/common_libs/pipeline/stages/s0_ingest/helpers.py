# ====== Code Summary ======
# Stateless helpers for the S0 ingestion stage: SHA-256 hashing, extension extraction,
# MIME-type lookup, PDF page counting, and raster-page detection.  Heuristic PDF probes
# log a warning on a degraded fallback so the degradation is never truly silent.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class S0IngestHelpers:
    """
    Stateless utility helpers for the S0 ingestion stage.

    All methods are pure functions with no dependency on external services or instance
    state.  The bound logger is only used to surface degraded heuristic fallbacks (page
    count / raster detection) so a malformed PDF never degrades silently.
    """

    logger = loggerplusplus.bind(identifier="S0IngestHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only class."""
        raise TypeError("S0IngestHelpers is a static-only class and cannot be instantiated.")

    # ─── MIME type lookup table (module-level constant) ────────────────────────
    _MIME_MAP: dict[str, str] = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
        "odt": "application/vnd.oasis.opendocument.text",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "rtf": "application/rtf",
        "txt": "text/plain",
        "html": "text/html",
        "htm": "text/html",
        "csv": "text/csv",
    }

    @staticmethod
    def sha256(data: bytes) -> str:
        """
        Compute the SHA-256 hex digest of raw file bytes.

        Used as the content-address key for all S3 artifacts.

        Args:
            data (bytes): Raw file bytes to hash.

        Returns:
            str: Lowercase hex SHA-256 digest.
        """
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def extract_extension(filename: str) -> str:
        """
        Return the lowercase file extension without the leading dot.

        Falls back to ``"bin"`` when no dot is present in the filename.

        Args:
            filename (str): Original filename (e.g. ``"report.docx"``).

        Returns:
            str: Lowercase extension (e.g. ``"docx"``), or ``"bin"`` if absent.
        """
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return "bin"

    @staticmethod
    def mime_type(extension: str) -> str:
        """
        Return a best-effort MIME type string for the given file extension.

        Falls back to ``"application/octet-stream"`` for unknown extensions.

        Args:
            extension (str): Lowercase file extension without the leading dot.

        Returns:
            str: MIME type string (e.g. ``"application/pdf"``).
        """
        return S0IngestHelpers._MIME_MAP.get(extension, "application/octet-stream")

    @classmethod
    def count_pages_fast(cls, pdf_bytes: bytes) -> int:
        """
        Count the number of pages in a PDF using PyMuPDF without a full parse.

        Returns 1 as a safe fallback if PyMuPDF is unavailable or the bytes are
        not a valid PDF.  The fallback is a degraded heuristic (S1 is the authority
        on the real page count), so it is logged rather than raised — but never silent.

        Args:
            pdf_bytes (bytes): Raw PDF bytes.

        Returns:
            int: Page count, or 1 on error.
        """
        try:
            import fitz
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                return doc.page_count
        except Exception as exc:
            cls.logger.warning(
                f"count_pages_fast: PyMuPDF could not read the PDF ({exc}); defaulting to 1 page."
            )
            return 1

    @classmethod
    def detect_raster_pages(cls, pdf_bytes: bytes) -> bool:
        """
        Return True if at least one page has no extractable text layer.

        Per spec §4.2: PyMuPDF.get_text() empty → scanned/raster page.
        Pages with a native text layer never need OCR (spec cost-saving principle 1).
        A probe failure is a degraded heuristic (OCR routing happens later in S2 anyway),
        so it is logged and treated as "no raster pages" — but never silent.

        Args:
            pdf_bytes (bytes): Raw PDF bytes.

        Returns:
            bool: True when OCR will be needed for at least one page; False otherwise.
        """
        try:
            import fitz
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                for page in doc:
                    if not page.get_text().strip():
                        return True
        except Exception as exc:
            cls.logger.warning(
                f"detect_raster_pages: PyMuPDF probe failed ({exc}); assuming no raster pages."
            )
        return False

    @staticmethod
    def build_implicit_meta(
        *,
        filename: str,
        original_format: str,
        file_size: int,
        source_hash: str,
        page_count: int,
        needs_ocr: bool,
    ) -> dict[str, Any]:
        """
        Build the file-intrinsic implicit metadata dictionary (spec §7.3).

        This dict is stored alongside the S0Result and surfaced to downstream
        stages as read-only context about the original file.

        Args:
            filename (str): Original upload filename.
            original_format (str): Lowercase file extension (e.g. ``"docx"``).
            file_size (int): Size of the original file in bytes.
            source_hash (str): SHA-256 hex digest of the original bytes.
            page_count (int): Number of pages in the derived PDF.
            needs_ocr (bool): True when at least one page was detected as raster.

        Returns:
            dict[str, Any]: Implicit metadata keyed by spec field names.
        """
        return {
            "filename": filename,
            "extension": original_format,
            "file_size": file_size,
            "source_hash": source_hash,
            "page_count": page_count,
            "has_scanned_pages": needs_ocr,
        }
