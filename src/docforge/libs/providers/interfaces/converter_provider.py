# ====== Code Summary ======
# ConverterProvider Protocol — defines the interface for document-to-PDF conversion backends
# (e.g. Gotenberg via LibreOffice + Chromium). Any converter adapter must satisfy this Protocol.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only)
# ====== Internal Project Imports ======
from libs.providers.results import ConvertResult

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class ConverterProvider(Protocol):
    """Converts office/web documents to PDF (e.g. Gotenberg → LibreOffice + Chromium)."""

    name: str
    version: str

    async def convert(self, data: bytes, filename: str) -> ConvertResult:
        """
        Convert document bytes to PDF.

        Args:
            data (bytes): Raw source file bytes.
            filename (str): Original filename (extension used to pick conversion path).

        Returns:
            ConvertResult: PDF bytes and page count.
        """
        ...
