# ====== Code Summary ======
# DocumentViewHelpers — turns a document's stored IR into an on-the-fly markdown or HTML VIEW
# (invariant #1: those formats are generated views, the IR is the source). It owns the small
# orchestration the two view endpoints share: adapt the DB-shaped IRBundle to a canonical
# DocumentIR, run the pure IRLinearizer, and wrap the string in a Response with the right
# content-type and an optional attachment Content-Disposition derived from the document's filename.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib
from urllib.parse import quote

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
        if download:
            headers["Content-Disposition"] = DocumentViewHelpers._content_disposition(
                filename, extension
            )

        return Response(content=body, media_type=media_type, headers=headers)

    @staticmethod
    def _content_disposition(filename: str, extension: str) -> str:
        """
        Build an RFC 6266 ``Content-Disposition`` value safe for non-latin-1 filenames.

        HTTP header values are latin-1; a filename with accents or CJK characters would crash when
        the header is encoded. A pure-ASCII name uses the plain ``filename=`` parameter; anything
        else emits an ASCII-sanitized ``filename=`` fallback for legacy clients plus an RFC 5987
        ``filename*`` carrying the full UTF-8 name percent-encoded (the form modern browsers prefer).

        Args:
            filename (str): The source document filename (supplies the download stem).
            extension (str): The generated view extension (``md`` or ``html``).

        Returns:
            str: A ``Content-Disposition`` header value that never raises on latin-1 encoding.
        """
        # 1. Derive the download stem, stripping quotes/newlines that could corrupt the parameter.
        raw_stem = pathlib.Path(filename or "document").stem
        stem = "".join(c for c in raw_stem if c not in '"\r\n') or "document"
        full_name = f"{stem}.{extension}"

        # 2. A pure-ASCII name needs only the plain filename= parameter (latin-1 safe as-is).
        try:
            full_name.encode("ascii")
        except UnicodeEncodeError:
            pass
        else:
            return f'attachment; filename="{full_name}"'

        # 3. Non-ASCII: ASCII fallback for legacy clients + RFC 5987 filename* with the full name.
        ascii_stem = stem.encode("ascii", "ignore").decode("ascii").strip() or "document"
        ascii_name = f"{ascii_stem}.{extension}"
        encoded = quote(full_name, safe="")
        return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


__all__ = ["DocumentViewHelpers"]
