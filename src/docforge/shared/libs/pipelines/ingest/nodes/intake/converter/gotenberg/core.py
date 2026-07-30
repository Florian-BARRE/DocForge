# ====== Code Summary ======
# The Gotenberg converter node — the first concrete child of BaseConverterNode. Routes by the
# PROBED format: office documents go to Gotenberg's LibreOffice route, HTML to its Chromium route,
# anything else has no PDF view (None → the base degrades). Pure HTTP client — Gotenberg runs as a
# service; its endpoint comes from the config.

# ====== Standard Library Imports ======
from pathlib import PurePosixPath

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SourceDocument, SourceProbe

# ====== Local Project Imports ======
from ..base import BaseConverterNode
from .config import ConverterGotenbergConfig


@NodeRegistry.register("converter")
class ConverterGotenbergNode(BaseConverterNode):
    """
    Convert office/HTML sources to PDF through a Gotenberg service.

    Office formats (docx, xlsx, pptx, odt, txt, md…) go through the LibreOffice route; HTML goes
    through the Chromium route. The probed format decides — never the file extension.
    """

    KIND = "gotenberg"
    UNIQUE_IN_GRAPH = True
    NAME = "Gotenberg"
    SUMMARY = "Convert office and HTML sources to PDF via a Gotenberg service."
    HOW_IT_WORKS = (
        "POSTs the file to the Gotenberg HTTP API — the LibreOffice route for office formats, the "
        "Chromium route for HTML — and returns the produced PDF bytes."
    )
    Config = ConverterGotenbergConfig

    # Probed formats handled by Gotenberg's LibreOffice route: modern, legacy and ODF office
    # formats, the plain-text family, and images (LibreOffice wraps an image into a one-page PDF —
    # a photographed document then follows the scanned/OCR path downstream).
    OFFICE_FORMATS = frozenset(
        {
            "docx",
            "doc",
            "xlsx",
            "xls",
            "pptx",
            "ppt",
            "odt",
            "ods",
            "odp",
            "rtf",
            "csv",
            "txt",
            "md",
            "png",
            "jpeg",
        }
    )

    async def preflight(self) -> None:
        """Verify the Gotenberg service is reachable before any conversion spend.

        Gotenberg is the one provider-hosted node on the intake path; without this it was the only
        external endpoint preflight could not check. Probes its ``/health`` route — any answer
        proves the host is up.
        """
        config: ConverterGotenbergConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            path="/health",
        )

    async def _convert(self, source: SourceDocument, probe: SourceProbe) -> bytes | None:
        """Route by probed format and run the conversion (None when Gotenberg can't handle it)."""
        config: ConverterGotenbergConfig = self.config

        # 1. Pick the Gotenberg route from what the bytes really are. The upload name's extension
        #    is NORMALIZED to the detected format — LibreOffice picks its import filter from the
        #    extension, so a lying filename would derail the conversion.
        stem = PurePosixPath(source.filename.replace("\\", "/")).stem or "document"
        if probe.format in self.OFFICE_FORMATS:
            route = "/forms/libreoffice/convert"
            upload_name = f"{stem}.{probe.format}"
        elif probe.format == "html":
            route = "/forms/chromium/convert/html"
            upload_name = "index.html"  # the Chromium route requires this exact name
        else:
            return None

        # 2. POST the file; Gotenberg answers with the PDF bytes.
        async with httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        ) as client:
            response = await client.post(
                route, files={"files": (upload_name, source.content, probe.mime_type)}
            )
            response.raise_for_status()
        self.logger.debug(
            f"Gotenberg converted '{source.filename}' ({probe.format}) → {len(response.content)} bytes"
        )
        return response.content


__all__ = ["ConverterGotenbergNode"]
