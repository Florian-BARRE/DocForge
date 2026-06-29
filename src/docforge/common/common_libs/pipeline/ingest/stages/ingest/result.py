# ====== Code Summary ======
# IngestResult dataclass — the canonical output contract of the ingest stage. It is the artefact
# every downstream consumer reads (parse, the worker node-cache codec, the persist/trace layer):
# the content-address (sha256), the object-store keys, the derived PDF, the page count, the OCR
# fork flag, and the file-intrinsic implicit metadata. Kept in its own module so it can be imported
# without pulling in the stage's converter / object-store dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IngestResult:
    """
    Output artefacts produced by the ingest stage.

    All downstream stages (parse, …) receive this object instead of raw bytes.

    Attributes:
        doc_id (str): Document UUID assigned at ingestion.
        source_hash (str): SHA-256 hex of original bytes (content-address key).
        original_key (str): Object-store key: ``originals/{source_hash}``.
        pdf_bytes (bytes | None): PDF for parsing; None = lazy (load from pdf_key). An IngestResult
            is restored from the node cache with ``pdf_bytes=None``; the engine downloads the PDF
            from the object store (``pdf_key``) before invoking parse if needed.
        pdf_key (str): Object-store key: ``derived/{source_hash}/pdf``.
        page_count (int): Total page count.
        original_filename (str): Original filename as provided by the uploader.
        original_format (str): File extension (lowercase, no dot).
        file_size (int): Original file size in bytes.
        needs_ocr (bool): True when at least one page was detected as raster.
        implicit_meta (dict[str, Any]): File-intrinsic metadata (filename, extension, size,
            source_hash, page_count, needs_ocr).
    """

    doc_id: str
    source_hash: str            # SHA-256 hex of original bytes (content-address key)
    original_key: str           # Object-store key: originals/{source_hash}
    # pdf_bytes is None when an IngestResult is restored from the node cache.
    # The engine downloads the PDF from the object store (pdf_key) before invoking parse if needed.
    pdf_bytes: bytes | None     # PDF for parsing; None = lazy (load from pdf_key)
    pdf_key: str                # Object-store key: derived/{source_hash}/pdf
    page_count: int             # Total page count
    original_filename: str
    original_format: str        # File extension (lowercase, no dot)
    file_size: int              # Original file size in bytes
    needs_ocr: bool             # True when at least one page was detected as raster
    implicit_meta: dict[str, Any] = field(default_factory=dict)


__all__ = ["IngestResult"]
