# ====== Code Summary ======
# PdfiumRenderer — the ONE gate to PDFium for the parse stage. PDFium is documented as NOT
# thread-safe, and the worker runs several jobs on a thread pool (WORKER_CONCURRENCY jobs, each
# rasterising off the event loop), so two concurrent renders in one process crash it (SIGSEGV /
# SIGTRAP, issue #242). Every PDFium call — open the document, rasterise a page, convert it to PIL
# and every close — runs while holding ONE process-wide lock; the lock is held per call (not per
# document), so a render's PNG encoding and cropping, which are pure PIL, never block another job.
# pypdfium2 is lazy-imported (native lib shipped in the worker image only). No config, no I/O.

# ====== Standard Library Imports ======
import threading
from types import TracebackType
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class PdfiumRenderer(LoggerClass):
    """Open one PDF and rasterise its pages, serialising every PDFium call process-wide."""

    # PDFium is not thread-safe: ONE lock for the whole process, shared by every instance. It is
    # taken inside the worker thread only, so the event loop is never blocked.
    _pdfium_lock = threading.Lock()

    def __init__(self, pdf_bytes: bytes, scale: float) -> None:
        """
        Open the document (under the PDFium lock).

        Args:
            pdf_bytes (bytes): The PDF to rasterise.
            scale (float): Rasterisation scale (1.0 ≈ 72 dpi; 2.0 ≈ 144 dpi).
        """
        LoggerClass.__init__(self)
        # 1. Lazy import — pypdfium2 is a native lib shipped in the worker image only.
        import pypdfium2 as pdfium

        self._scale = scale
        with self._pdfium_lock:
            self._document: Any = pdfium.PdfDocument(pdf_bytes)

    def __enter__(self) -> "PdfiumRenderer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __len__(self) -> int:
        """Return the number of pages of the document."""
        with self._pdfium_lock:
            return len(self._document)

    def render_page(self, index: int) -> Any:
        """
        Rasterise one page to a PIL image.

        The page and its bitmap are closed explicitly inside the lock: left to the garbage
        collector, their PDFium destructors would run later, outside the lock.

        Args:
            index (int): 0-indexed page number.

        Returns:
            PIL.Image.Image: The page raster, independent of PDFium (safe to use unlocked).
        """
        with self._pdfium_lock:
            page = self._document[index]
            try:
                bitmap = page.render(scale=self._scale)
                try:
                    return bitmap.to_pil()
                finally:
                    bitmap.close()
            finally:
                page.close()

    def close(self) -> None:
        """Close the document (under the PDFium lock); safe to call twice."""
        with self._pdfium_lock:
            self._document.close()
        self.logger.debug("PDFium document closed")


__all__ = ["PdfiumRenderer"]
