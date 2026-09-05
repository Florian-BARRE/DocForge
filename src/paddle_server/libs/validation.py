# ====== Code Summary ======
# Cheap, paddle-free validation that a raw request body actually decodes as the media type its route
# expects (an image for /ocr, a PDF for /layout-parsing). Runs BEFORE the expensive predict(): a
# malformed/undecodable upload is a CLIENT error, so it is rejected as `InvalidInputError` (mapped to
# HTTP 422 by the router) instead of reaching PaddleX and surfacing a raw exception string at HTTP 500
# — which both mis-signals a server fault and leaks internal detail. Genuine server faults still fall
# through to `@auto_handle_errors` -> HTTP 500.
#
# Pillow / pypdfium2 are both AVX-free and already pulled in transitively by paddlex[ocr]; their
# imports are deferred into the methods so importing this module never touches the PaddlePaddle stack
# (keeps the module unit-testable on an AVX-less CPU, matching the normalizer discipline).

# ====== Standard Library Imports ======
from __future__ import annotations

import io

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class InvalidInputError(ValueError):
    """
    Raised when a request body cannot be decoded as the media type its route expects.

    A client error (bad upload), NOT a server fault — the router maps it to HTTP 422 with a clean,
    non-leaky message, distinct from the HTTP 500 reserved for genuine internal failures.
    """


class InputValidator:
    """
    Static-only validators that a raw request body decodes as a supported image / PDF.

    Each method raises `InvalidInputError` on an undecodable body and returns None otherwise.
    Never instantiated (mirrors the sidecar's other static helpers).
    """

    logger = loggerplusplus.bind(identifier="InputValidator")

    def __new__(cls, *args: object, **kwargs: object) -> InputValidator:
        raise TypeError("InputValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def verify_image(cls, data: bytes) -> None:
        """
        Verify that raw bytes decode as a supported image, without a full pixel decode.

        Args:
            data (bytes): The request body (the image bytes).

        Raises:
            InvalidInputError: If the bytes are not a decodable image.
        """
        # 1. Defer Pillow's import so importing this module never loads it (test/AVX discipline).
        from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

        # 2. Pillow's `verify()` checks structural integrity cheaply (no full decode); it consumes
        #    the object, which is fine — predict() re-reads the bytes from the temp file downstream.
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
            cls.logger.warning(f"Rejected undecodable image body ({len(data)} bytes): {exc}")
            raise InvalidInputError("request body is not a decodable image") from exc

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

        # 2. Opening is lazy (no page rendering) — this only parses the document structure and
        #    reads the page count, so it stays cheap even for a large PDF.
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
