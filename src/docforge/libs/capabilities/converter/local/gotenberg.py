# ====== Code Summary ======
# Gotenberg HTTP client — wraps LibreOffice + Chromium conversion behind a clean async API.
# Gotenberg is the only converter in DocForge (spec ADR-3).
# Supports: office formats (docx/doc/pptx/odt/rtf…) → PDF via LibreOffice.
# PDF page count is extracted with PyMuPDF after conversion.
# Config id: "gotenberg"

# ====== Standard Library Imports ======
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
import fitz  # PyMuPDF
import httpx
from loggerplusplus import LoggerClass
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.capabilities._registry import register
from libs.capabilities.converter.base import ConverterProvider
from libs.capabilities.interfaces import ConvertResult


# Formats routed through Gotenberg (office → LibreOffice → PDF)
GOTENBERG_FORMATS: frozenset[str] = frozenset(
    {
        "docx", "doc", "docm",
        "xlsx", "xls", "xlsm",
        "pptx", "ppt", "pptm",
        "odt", "ods", "odp",
        "rtf", "txt", "html", "htm",
        "csv",  # LibreOffice can open CSV → formatted PDF
    }
)

# PDF formats that go directly to S1 (no Gotenberg call needed)
NATIVE_PDF_FORMATS: frozenset[str] = frozenset({"pdf"})


class GotenbergConverter(ConverterProvider, LoggerClass):
    """
    Async Gotenberg client implementing the ``ConverterProvider`` Protocol.

    Sends documents to the Gotenberg HTTP API and returns PDF bytes.
    Gotenberg wraps LibreOffice (macros disabled) and Chromium in an ops-grade container.

    Endpoints used:
        POST /forms/libreoffice/convert  — office formats → PDF
    """

    name: str = "gotenberg"
    version: str = "8"

    def __init__(self, base_url: str, timeout_s: int = 120) -> None:
        """
        Initialize the Gotenberg client.

        Args:
            base_url (str): Gotenberg service URL, e.g. ``http://gotenberg:3000``.
            timeout_s (int): HTTP request timeout in seconds.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def convert(self, data: bytes, filename: str) -> ConvertResult:
        """
        Convert a document to PDF via Gotenberg.

        Only office formats are routed here (see ``GOTENBERG_FORMATS``).
        PDF files must NOT be passed to this method — call raises ``ValueError``.

        Args:
            data (bytes): Raw source file bytes.
            filename (str): Original filename (extension determines the conversion path).

        Returns:
            ConvertResult: PDF bytes and page count.

        Raises:
            ValueError: If the filename extension is not a supported office format.
            httpx.HTTPStatusError: On non-2xx Gotenberg response.
        """
        # 1. Validate extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in GOTENBERG_FORMATS:
            raise ValueError(
                f"GotenbergConverter does not handle extension {ext!r}. "
                f"Supported: {sorted(GOTENBERG_FORMATS)}"
            )

        self.logger.debug(f"Converting {filename!r} ({len(data)} bytes) via Gotenberg…")

        # 2. POST to Gotenberg's LibreOffice endpoint
        pdf_bytes = await self._post_libreoffice(data=data, filename=filename)

        # 3. Extract page count from the resulting PDF
        page_count = self._count_pages(pdf_bytes)

        self.logger.info(
            f"Converted {filename!r} → PDF ({len(pdf_bytes)} bytes, {page_count} pages)"
        )
        return ConvertResult(pdf_bytes=pdf_bytes, page_count=page_count)

    async def health_check(self) -> bool:
        """
        Ping the Gotenberg health endpoint.

        Returns:
            bool: True if Gotenberg is reachable and healthy.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    # ─── Private helpers ───────────────────────────────────────────────────────

    async def _post_libreoffice(self, data: bytes, filename: str) -> bytes:
        """
        POST the file to the Gotenberg LibreOffice conversion endpoint.

        Gotenberg accepts multipart/form-data with the file under the ``files`` field.
        Macros are disabled by default in Gotenberg 8 (security best practice).
        """
        url = f"{self._base_url}/forms/libreoffice/convert"

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                url,
                files={"files": (filename, io.BytesIO(data), "application/octet-stream")},
            )
            response.raise_for_status()
            return response.content

    @staticmethod
    def _count_pages(pdf_bytes: bytes) -> int:
        """
        Count PDF pages using PyMuPDF without writing to disk.

        Args:
            pdf_bytes (bytes): Valid PDF bytes.

        Returns:
            int: Total page count.
        """
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return doc.page_count

    @staticmethod
    def needs_conversion(filename: str) -> bool:
        """
        Return True if this filename needs to go through Gotenberg.

        Args:
            filename (str): Original filename with extension.

        Returns:
            bool: True for office formats, False for native PDF.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext in GOTENBERG_FORMATS


# ─── Config ──────────────────────────────────────────────────────────────────


def _flatten_provider_spec(v: Any) -> Any:
    """Backward compat: accept old ProviderSpec {id, params} format."""
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


@register("converter")
class GotenbergConfig(BaseModel):
    """
    Configuration for the Gotenberg document converter.

    Config id: "gotenberg" — LibreOffice + Chromium conversion via the Gotenberg HTTP API.

    Attributes:
        id: Provider discriminator — always "gotenberg".
        base_url: Gotenberg service URL (e.g. http://gotenberg:3000).
        timeout_s: HTTP conversion timeout in seconds.
    """

    _label: ClassVar[str] = "Gotenberg — LibreOffice + Chromium PDF/DOCX/HTML converter"
    _category: ClassVar[str] = "converter"

    id: Literal["gotenberg"] = "gotenberg"
    base_url: str = Field(default="http://gotenberg:3000", description="Gotenberg service URL.")
    timeout_s: int = Field(default=120, ge=10, le=600, description="HTTP timeout in seconds.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> "GotenbergConverter":
        """Instantiate GotenbergConverter from this config."""
        return GotenbergConverter(base_url=self.base_url, timeout_s=self.timeout_s)

    def merge_defaults(self, cfg: Any) -> "GotenbergConfig":
        """Merge deployment env defaults (base_url from RUNTIME_CONFIG)."""
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "GOTENBERG_URL", self.base_url),
            "timeout_s": self.timeout_s,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Check Gotenberg availability — always available (no import check needed)."""
        base_url = getattr(cfg, "GOTENBERG_URL", "")
        return True, f"Gotenberg at {base_url}" if base_url else "URL configurable"
