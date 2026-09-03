# ====== Code Summary ======
# DocumentViewHelpers — turns a document's stored IR into an on-the-fly markdown or HTML VIEW
# (invariant #1: those formats are generated views, the IR is the source). It owns the small
# orchestration the two view endpoints share: adapt the DB-shaped IRBundle to a canonical
# DocumentIR, run the pure IRLinearizer, and wrap the string in a Response with the right
# content-type and an optional attachment Content-Disposition derived from the document's filename.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib

# ====== Third-Party Library Imports ======
from fastapi import Response
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.linearize import IRLinearizer
from shared_libs.services.db.facades import IRBundle
from shared_libs.services.db.postgresql.tables import Document

# ====== Local Project Imports ======
from .ir_adapter import IRBundleAdapter

# Charset-qualified media types — the body is a unicode string, always encoded as UTF-8.
_MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
_HTML_MEDIA_TYPE = "text/html; charset=utf-8"


class DocumentViewHelpers:
    """Render a document's IR as a markdown/HTML Response, inline or as a download."""

    logger = loggerplusplus.bind(identifier="DocumentViewHelpers")

    # Stateless, pure emitter — safe to build once and reuse across requests.
    _linearizer = IRLinearizer()

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentViewHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def markdown(cls, document: Document, bundle: IRBundle, download: bool) -> Response:
        """
        Render the document as a markdown view Response.

        Args:
            document (Document): The document row (supplies the download filename stem).
            bundle (IRBundle): The document's stored IR rows.
            download (bool): When True, attach a Content-Disposition so browsers save the file.

        Returns:
            Response: The markdown body as ``text/markdown; charset=utf-8``.
        """
        # 1. Adapt the DB rows to the canonical IR, then linearize to markdown.
        ir = IRBundleAdapter.to_document_ir(document, bundle)
        body = cls._linearizer.to_markdown(ir)

        # 2. Wrap with the markdown media type and the ".md" download name.
        return cls._response(body, _MARKDOWN_MEDIA_TYPE, document.filename, "md", download)

    @classmethod
    def html(cls, document: Document, bundle: IRBundle, download: bool) -> Response:
        """
        Render the document as an HTML view Response.

        Args:
            document (Document): The document row (supplies the download filename stem).
            bundle (IRBundle): The document's stored IR rows.
            download (bool): When True, attach a Content-Disposition so browsers save the file.

        Returns:
            Response: The HTML body as ``text/html; charset=utf-8``.
        """
        # 1. Adapt the DB rows to the canonical IR, then linearize to HTML.
        ir = IRBundleAdapter.to_document_ir(document, bundle)
        body = cls._linearizer.to_html(ir)

        # 2. Wrap with the HTML media type and the ".html" download name.
        return cls._response(body, _HTML_MEDIA_TYPE, document.filename, "html", download)

    @staticmethod
    def _response(
        body: str, media_type: str, filename: str, extension: str, download: bool
    ) -> Response:
        """Wrap a rendered view in a Response, adding an attachment header only for a download."""
        # 1. Inline by default — no Content-Disposition means the browser renders it in place.
        headers: dict[str, str] = {}

        # 2. For a download, name the file after the source stem so "report.pdf" -> "report.md".
        #    Strip quotes/newlines so a hostile filename can't corrupt the Content-Disposition param.
        if download:
            raw_stem = pathlib.Path(filename or "document").stem
            stem = "".join(c for c in raw_stem if c not in '"\r\n') or "document"
            headers["Content-Disposition"] = f'attachment; filename="{stem}.{extension}"'

        return Response(content=body, media_type=media_type, headers=headers)


__all__ = ["DocumentViewHelpers"]
