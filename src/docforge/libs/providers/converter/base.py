# ====== Code Summary ======
# Abstract base class for all document conversion providers.
# Every converter takes raw office/web bytes and produces a PDF.

from __future__ import annotations

from abc import ABC, abstractmethod

from libs.capabilities.interfaces import ConvertResult


class ConverterProvider(ABC):
    """
    Abstract base class for all document conversion providers.

    Converts office documents (DOCX, XLSX, PPTX, HTML, …) into PDF bytes,
    handling all format-specific details internally.

    Subclasses target a specific conversion engine (LibreOffice via Gotenberg,
    a cloud API, etc.) and are instantiated by StageEngine / ProviderRegistry.

    Class attributes:
        name (str): Provider identifier used in logs.
        version (str): Engine version string.
    """

    name: str
    version: str

    @abstractmethod
    async def convert(self, data: bytes, filename: str) -> ConvertResult:
        """
        Convert document bytes to PDF.

        Args:
            data (bytes): Raw source file bytes.
            filename (str): Original filename — extension selects the conversion path.

        Returns:
            ConvertResult: PDF bytes and page count.

        Raises:
            ValueError: When the file extension is not supported by this provider.
            httpx.HTTPStatusError: On conversion engine API error.
        """
        ...
