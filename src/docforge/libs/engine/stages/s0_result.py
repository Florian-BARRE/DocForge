# ====== Code Summary ======
# S0Result dataclass — output artefacts produced by the S0 ingestion stage.
# Extracted from s0_ingest.py to keep the result model separately importable
# without pulling in all of S0IngestStage's dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class S0Result:
    """
    Output artefacts produced by the S0 ingestion stage.

    All downstream stages (S1…) receive this object instead of raw bytes.

    Attributes:
        doc_id (str): Document UUID assigned at ingestion.
        source_hash (str): SHA-256 hex of original bytes (content-address key).
        original_key (str): Object-store key: ``originals/{source_hash}``.
        pdf_bytes (bytes | None): PDF for S1 parsing; None = lazy (load from pdf_key).
            S0Result is restored from the P2 node cache with pdf_bytes=None;
            the engine downloads the PDF from S3 (pdf_key) before invoking S1 if needed.
        pdf_key (str): Object-store key: ``derived/{source_hash}/pdf``.
        page_count (int): Total page count.
        original_filename (str): Original filename as provided by the uploader.
        original_format (str): File extension (lowercase, no dot).
        file_size (int): Original file size in bytes.
        needs_ocr (bool): True when at least one page was detected as raster.
        implicit_meta (dict[str, Any]): File-intrinsic metadata (filename, extension,
            size, source_hash, page_count, needs_ocr).
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
