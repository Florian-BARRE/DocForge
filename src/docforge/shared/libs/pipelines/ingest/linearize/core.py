# ====== Code Summary ======
# IRLinearizer — the public facade the app calls to turn the canonical DocumentIR into a full-document
# markdown or HTML VIEW on the fly (invariant #1: markdown/PDF/HTML are generated views, the IR is the
# source). It owns one markdown and one html emitter and delegates the walk to them. PURE: no I/O — a
# caller holding a DocumentIR gets a string back, nothing is read or written.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import DocumentIR

# ====== Local Project Imports ======
from .html import HtmlLinearizer
from .markdown import MarkdownLinearizer


class IRLinearizer(LoggerClass):
    """
    Public entry point for rendering a canonical DocumentIR as a linear document view.

    Holds a markdown and an HTML emitter (both stateless strategies over the shared reading-order
    walker) and exposes the two view methods the backend endpoint calls.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._markdown = MarkdownLinearizer()
        self._html = HtmlLinearizer()

    def to_markdown(self, ir: DocumentIR) -> str:
        """
        Render the whole document as markdown.

        Args:
            ir (DocumentIR): The canonical parsed document.

        Returns:
            str: The full-document markdown view.
        """
        return self._markdown.render(ir)

    def to_html(self, ir: DocumentIR) -> str:
        """
        Render the whole document as structural, escaped HTML.

        Args:
            ir (DocumentIR): The canonical parsed document.

        Returns:
            str: The full-document HTML view.
        """
        return self._html.render(ir)

    def to_html_body(self, ir: DocumentIR) -> str:
        """
        Render only the escaped HTML body fragment (no document skeleton).

        Args:
            ir (DocumentIR): The canonical parsed document (or a block subset of it).

        Returns:
            str: The body fragment, to be composed and wrapped by :meth:`to_html_document`.
        """
        return self._html.render_body(ir)

    def to_html_document(self, ir: DocumentIR, body: str) -> str:
        """
        Wrap an already-rendered (escaped) body in the standalone UTF-8 HTML5 skeleton.

        Args:
            ir (DocumentIR): The document supplying the language and title.
            body (str): The escaped body markup (e.g. several composed :meth:`to_html_body` outputs).

        Returns:
            str: The full HTML document.
        """
        return self._html.wrap_document(ir, body)


__all__ = ["IRLinearizer"]
