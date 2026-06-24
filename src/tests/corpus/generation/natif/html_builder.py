# ====== Code Summary ======
# HtmlCorpusBuilder — hand-authors a LONG, self-contained HTML document from a multilingual content
# pack: heading hierarchy, a CSS multi-column section, many prose sections (cycled to real length),
# a wide table with a colspan header AND a nested table, base64 data-URI figures, and a footnotes
# block. Self-contained (no external assets). Converted to PDF by LibreOffice/Chromium at ingest.
# Driven by spec.doc_type + spec.language.

# ====== Standard Library Imports ======
from __future__ import annotations

import base64

# ====== Local Project Imports ======
from .base import BaseDocumentBuilder
from .content import ContentPack, get_content
from .image_factory import ImageFactory

# Number of prose sections to emit (cycling the content pool) — drives length + chunking.
_SECTIONS = 10


class HtmlCorpusBuilder(BaseDocumentBuilder):
    """Builds a long, complex, self-contained HTML document for one (doc_type, language)."""

    def build(self) -> bytes:
        """
        Assemble the HTML document and return its UTF-8 bytes.

        Returns:
            bytes: A long, self-contained .html document.
        """
        # 1. Resolve content + embed two figures as base64 data-URIs (no external assets)
        content = get_content(self.spec.doc_type, self.spec.language)
        chart_uri = self.__data_uri(ImageFactory.bar_chart("KPI"))
        diagram_uri = self.__data_uri(ImageFactory.diagram())

        # 2. Compose the document from focused fragments
        html = (
            f"<!DOCTYPE html>\n<html lang=\"{content.language}\">\n<head>\n"
            f"<meta charset=\"utf-8\"/>\n<title>{content.title}</title>\n"
            f"{self.__style()}\n</head>\n<body>\n"
            f"<h1>{content.title}</h1>\n<p class='subtitle'>{content.subtitle}</p>\n"
            f"<p class='abstract'>{content.abstract}</p>\n"
            f"{self.__columns(content)}\n"
            f"{self.__sections(content)}\n"
            f"{self.__figure(chart_uri, content.table_caption)}\n"
            f"{self.__wide_table(content)}\n"
            f"{self.__figure(diagram_uri, content.section_title(0))}\n"
            f"{self.__footnotes(content)}\n"
            "</body>\n</html>\n"
        )
        return html.encode("utf-8")

    @staticmethod
    def __style() -> str:
        """Return the inline stylesheet (multi-column + table + figure rules)."""
        return (
            "<style>\n"
            "  body { font-family: Georgia, serif; margin: 2.5em; color: #1a1a1a; line-height: 1.5; }\n"
            "  h1 { color: #4F46E5; } h2 { color: #312e81; } h3 { color: #555; }\n"
            "  .subtitle { font-style: italic; color: #666; }\n"
            "  .cols { column-count: 2; column-gap: 2em; text-align: justify; }\n"
            "  table { border-collapse: collapse; width: 100%; margin: 1em 0; }\n"
            "  th, td { border: 1px solid #777; padding: 5px 9px; font-size: 0.95em; }\n"
            "  th { background: #4F46E5; color: white; }\n"
            "  figure { margin: 1.5em 0; } figcaption { font-style: italic; color: #444; }\n"
            "  .footnotes { font-size: 0.85em; color: #444; border-top: 1px solid #ccc; }\n"
            "</style>"
        )

    @staticmethod
    def __columns(content: ContentPack) -> str:
        """Return a two-column (CSS) section carrying the repeated governance blurb."""
        blurb = " ".join([content.column_blurb] * 3)
        return f"<section class='cols'><p>{blurb}</p></section>"

    def __sections(self, content: ContentPack) -> str:
        """Return many prose sections (H2 + paragraphs, with an H3 sub-section) for real length."""
        out: list[str] = []
        for i in range(_SECTIONS):
            out.append(f"<h2>{i + 1}. {content.section_title(i)}</h2>")
            out.append(f"<p>{content.para(i)}</p><p>{content.para(i + 1)}</p>")
            out.append(f"<h3>{content.section_title(i + 1)}</h3><p>{content.para(i + 2)}</p>")
        return "\n".join(out)

    @staticmethod
    def __wide_table(content: ContentPack) -> str:
        """Return the wide table (colspan header) with a nested table in the last data cell."""
        heads = "".join(f"<th>{h}</th>" for h in content.table_headers)
        body_rows = []
        for r, row in enumerate(content.table_rows):
            cells = "".join(f"<td>{c}</td>" for c in row[:-1])
            last = row[-1]
            if r == 0:  # nest a small table inside the first row's last cell
                last = "<table><tr><th>Sous-poste</th><th>Valeur</th></tr>" \
                       "<tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></table>"
            body_rows.append(f"<tr>{cells}<td>{last}</td></tr>")
        return (
            f"<h2>{content.table_caption}</h2><table>"
            f"<thead><tr><th colspan='{len(content.table_headers)}'>{content.table_caption}</th></tr>"
            f"<tr>{heads}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
        )

    @staticmethod
    def __figure(data_uri: str, caption: str) -> str:
        """Return a <figure> with an embedded data-URI image + caption."""
        return f"<figure><img src='{data_uri}' alt='{caption}' width='520'/><figcaption>{caption}</figcaption></figure>"

    @staticmethod
    def __footnotes(content: ContentPack) -> str:
        """Return a footnotes block (ordered list of the pack's notes)."""
        items = "".join(f"<li>{n}</li>" for n in content.notes)
        return f"<section class='footnotes'><h3>Notes</h3><ol>{items}</ol></section>"

    @staticmethod
    def __data_uri(png: bytes) -> str:
        """Encode PNG bytes as a base64 data-URI suitable for an <img src>."""
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
