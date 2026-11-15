# ====== Code Summary ======
# PdfDecoder: verifies that raw bytes are a PDF with at least one page, using pypdfium2 (lazy, no page
# rendering). pypdfium2 is NOT a dependency of the core: the model server that wants this decoder
# depends on it, and the import is deferred so importing the core never loads it.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from model_server_core.errors import InvalidInputError

# ====== Local Project Imports ======
from .media_decoder import MediaDecoder, MediaKind


class PdfDecoder(MediaDecoder, LoggerClass):
    """PDF check backed by pypdfium2 (provided by the model server, imported lazily)."""

    kind = MediaKind.PDF

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def verify(self, data: bytes) -> None:
        """Verify that `data` decodes as a PDF with at least one page.

        Args:
            data (bytes): The request body (the PDF bytes).

        Raises:
            InvalidInputError: If the bytes are not a decodable PDF or contain no pages.
            ModuleNotFoundError: If the server did not depend on pypdfium2 (a wiring error).
        """
        # 1. Deferred import: pypdfium2 belongs to the server that uses this decoder.
        import pypdfium2 as pdfium  # noqa: PLC0415

        # 2. Opening is lazy (no rendering): this only parses the structure and reads the page count.
        try:
            document = pdfium.PdfDocument(data)
            try:
                page_count = len(document)
            finally:
                document.close()
        except pdfium.PdfiumError as exc:
            self.logger.warning(f"Rejected undecodable PDF body ({len(data)} bytes): {exc}")
            raise InvalidInputError("request body is not a decodable PDF") from exc

        if page_count < 1:
            self.logger.warning(f"Rejected PDF body with no pages ({len(data)} bytes)")
            raise InvalidInputError("request body is a PDF with no pages")
