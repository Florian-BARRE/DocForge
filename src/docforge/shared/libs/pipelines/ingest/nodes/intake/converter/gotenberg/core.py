# ====== Code Summary ======
# The Gotenberg converter node — the first concrete child of BaseConverterNode. Routes by the
# PROBED format: office documents go to Gotenberg's LibreOffice route; anything else has no PARSER
# PDF (None → the base degrades). Structured TEXT formats (html/md) are deliberately NOT converted
# for the parser — a PDF round-trip flattens their heading tree, so the parser reads their original
# bytes natively — but they DO get a view-only preview PDF via _preview (Chromium routes), a channel
# decoupled from parsing that feeds only the page-render + PDF-view. Pure HTTP client — Gotenberg
# runs as a service; its endpoint comes from the config.

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
    Convert office sources to PDF through a Gotenberg service.

    Office formats (docx, xlsx, pptx, odt, txt…) go through the LibreOffice route. HTML and
    markdown are NOT converted — they pass through (no PDF view) so the parser reads their
    original bytes natively, preserving the heading tree a PDF round-trip would flatten. The
    probed format decides — never the file extension.
    """

    KIND = "gotenberg"
    UNIQUE_IN_GRAPH = True
    NAME = "Gotenberg"
    SUMMARY = "Convert office sources to PDF via a Gotenberg service (html/md pass through)."
    HOW_IT_WORKS = (
        "POSTs office files to the Gotenberg HTTP API's LibreOffice route and returns the produced "
        "PDF bytes; html/md are left untouched for native parsing."
    )
    Config = ConverterGotenbergConfig

    # Probed formats handled by Gotenberg's LibreOffice route: modern, legacy and ODF office
    # formats, the plain-text family, and images (LibreOffice wraps an image into a one-page PDF —
    # a photographed document then follows the scanned/OCR path downstream). Structured text
    # formats (html/md) are excluded on purpose: they are parsed natively from their original
    # bytes, so a PDF conversion here would only destroy their structure.
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
            "png",
            "jpeg",
        }
    )

    # Structured text formats parsed NATIVELY (no parser PDF) that still deserve a view-only preview
    # PDF: Gotenberg's Chromium routes render them for the page-render + PDF-view channel only.
    PREVIEW_FORMATS = frozenset({"html", "md"})

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
        else:
            # Not office (incl. html/md, parsed natively downstream) — no PDF view from here.
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

    async def _preview(self, source: SourceDocument, probe: SourceProbe) -> bytes | None:
        """Render a VIEW-ONLY PDF for html/md via Gotenberg's Chromium routes (never parsed).

        HTML goes through the Chromium ``html`` route (the source IS the ``index.html``); markdown
        goes through the ``markdown`` route with a minimal ``index.html`` wrapper that pulls the
        markdown file in via Gotenberg's ``toHTML`` template. Any other format has no preview.
        """
        if probe.format not in self.PREVIEW_FORMATS:
            return None
        config: ConverterGotenbergConfig = self.config

        # Build the multipart form per route. Gotenberg keys every uploaded file under the repeated
        # "files" field and reads it by its filename — hence the list-of-tuples form.
        if probe.format == "md":
            stem = PurePosixPath(source.filename.replace("\\", "/")).stem or "document"
            md_name = f"{stem}.md"
            wrapper = (
                '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
                '{{ toHTML "' + md_name + '" }}</body></html>'
            )
            route = "/forms/chromium/convert/markdown"
            files = [
                ("files", ("index.html", wrapper.encode("utf-8"), "text/html")),
                ("files", (md_name, source.content, "text/markdown")),
            ]
        else:
            route = "/forms/chromium/convert/html"
            files = [("files", ("index.html", source.content, "text/html"))]

        async with httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        ) as client:
            response = await client.post(route, files=files)
            response.raise_for_status()
        self.logger.debug(
            f"Gotenberg preview-rendered '{source.filename}' ({probe.format}) → "
            f"{len(response.content)} bytes (view-only, not parsed)"
        )
        return response.content


__all__ = ["ConverterGotenbergNode"]
