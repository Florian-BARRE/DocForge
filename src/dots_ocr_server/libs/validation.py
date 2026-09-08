# ====== Code Summary ======
# Cheap, model-free validation that a raw request body actually decodes as a PDF (the media type the
# /parse route expects). Runs BEFORE the expensive GPU parse: a malformed/undecodable upload is a
# CLIENT error, so it is rejected as `InvalidInputError` (mapped to HTTP 422 by the router) instead of
# reaching the VLM and surfacing a raw exception string at HTTP 500 — which both mis-signals a server
# fault and leaks internal detail. Genuine server faults still fall through to `@auto_handle_errors`
# -> HTTP 500.
#
# pypdfium2 is AVX-free, lightweight, and a BASE dependency (it also renders the pages this sidecar
# feeds to the VLM), so importing this module never touches transformers/torch/CUDA — it stays unit-testable on
# this CPU-only VM.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class InvalidInputError(ValueError):
    """
    Raised when a request body cannot be decoded as the PDF media type the /parse route expects.

    A client error (bad upload), NOT a server fault — the router maps it to HTTP 422 with a clean,
    non-leaky message, distinct from the HTTP 500 reserved for genuine internal failures.
    """


class InputValidator:
    """
    Static-only validator that a raw request body decodes as a PDF with at least one page.

    Raises `InvalidInputError` on an undecodable body and returns None otherwise. Never instantiated
    (mirrors the sidecar's other static helpers).
    """

    logger = loggerplusplus.bind(identifier="InputValidator")

    def __new__(cls, *args: object, **kwargs: object) -> InputValidator:
        raise TypeError("InputValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def verify_pdf(cls, data: bytes) -> None:
        """
        Verify that raw bytes decode as a PDF with at least one page (no page rendering).

        Args:
            data (bytes): The request body (the PDF bytes).

        Raises:
            InvalidInputError: If the bytes are not a decodable PDF or contain no pages.
        """
        # 1. Defer pypdfium2's import so importing this module never loads it.
        import pypdfium2 as pdfium  # noqa: PLC0415

        # 2. Opening is lazy (no page rendering) — this only parses the document structure and reads
        #    the page count, so it stays cheap even for a large PDF.
        try:
            document = pdfium.PdfDocument(data)
            try:
                page_count = len(document)
            finally:
                document.close()
        except pdfium.PdfiumError as exc:
            cls.logger.warning(f"Rejected undecodable PDF body ({len(data)} bytes): {exc}")
            raise InvalidInputError("request body is not a decodable PDF") from exc

        if page_count < 1:
            cls.logger.warning(f"Rejected PDF body with no pages ({len(data)} bytes)")
            raise InvalidInputError("request body is a PDF with no pages")


__all__ = ["InputValidator", "InvalidInputError"]
