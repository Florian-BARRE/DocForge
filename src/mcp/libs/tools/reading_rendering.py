# ====== Code Summary ======
# Text renderers for the document-reading tools (outline, chunk context, chunk pages). They give an
# agent a compact, citation-first view instead of a JSON envelope. Separators are ASCII on purpose
# (runtime strings must survive a Windows console).

from __future__ import annotations

# ====== Third-Party Library Imports ======
from docforge_sdk.models import ChunkContext, ChunkInfo, ChunkPage, DocumentOutline

_PART_SEPARATOR = " | "
_HEADING_SEPARATOR = " > "
_INDENT = "  "


class ReadingTextRenderer:
    """Formats outline / context / chunk-page results as compact plain text."""

    def render_outline(self, outline: DocumentOutline) -> str:
        """
        Render a document outline as one indented line per heading.

        Args:
            outline (DocumentOutline): The outline from the SDK.

        Returns:
            str: A title line, then `<indent by level><text> | p.<page_number> | chunk <id>` lines.
        """
        # 1. Title line (page count only when known)
        pages = f" | {outline.page_count} pages" if outline.page_count is not None else ""
        title = outline.display_title or "(untitled)"
        lines = [f"{title}{pages} | doc {outline.document_id} | {len(outline.headings)} headings"]

        # 2. One line per heading, indented by depth; missing parts are omitted
        for heading in outline.headings:
            parts = [_INDENT * max(heading.level - 1, 0) + heading.text]
            if heading.page_number is not None:
                parts.append(f"p.{heading.page_number}")
            if heading.chunk_id:
                parts.append(f"chunk {heading.chunk_id}")
            lines.append(_PART_SEPARATOR.join(parts))
        return "\n".join(lines)

    def render_context(self, context: ChunkContext) -> str:
        """
        Render a chunk reading window; the target chunk is marked with `*`.

        Args:
            context (ChunkContext): The window from the SDK.

        Returns:
            str: A title line, then per chunk `[index{*}] p.N | heading` and its text.
        """
        lines = [f"{context.display_title or '(untitled)'} | doc {context.document_id}"]
        for chunk in context.chunks:
            marker = "*" if chunk.is_target else ""
            lines.append(
                self._chunk_line(
                    f"[{chunk.chunk_index}{marker}]", chunk.page_number, chunk.heading_path
                )
            )
            lines.append(chunk.text)
        return "\n".join(lines)

    def render_chunk_page(self, page: ChunkPage, offset: int) -> str:
        """
        Render one page of a document's chunks with its position in the total.

        Args:
            page (ChunkPage): The chunk page from the SDK.
            offset (int): The offset the page was requested with.

        Returns:
            str: A `chunks A-B of TOTAL` header, then one block per chunk.
        """
        count = len(page.items)
        total = "?" if page.total is None else str(page.total)
        span = f"{offset + 1}-{offset + count}" if count else "0"
        lines = [f"chunks {span} of {total}"]
        for chunk in page.items:
            lines.append(self._page_chunk_line(chunk))
            lines.append(chunk.text)
        return "\n".join(lines)

    def _page_chunk_line(self, chunk: ChunkInfo) -> str:
        """Citation line of one listed chunk (index, page, breadcrumb, tokens, id)."""
        line = self._chunk_line(f"[{chunk.chunk_index}]", chunk.page_number, chunk.heading_path)
        suffix = f"{chunk.token_count} tokens{'' if chunk.enabled else ' | disabled'}"
        return f"{line}{_PART_SEPARATOR}{suffix}{_PART_SEPARATOR}chunk {chunk.id}"

    @staticmethod
    def _chunk_line(label: str, page_number: int | None, heading_path: list[str]) -> str:
        """Join the label with the page and breadcrumb parts that exist."""
        parts: list[str] = []
        if page_number is not None:
            parts.append(f"p.{page_number}")
        if heading_path:
            parts.append(_HEADING_SEPARATOR.join(heading_path))
        return label + (" " + _PART_SEPARATOR.join(parts) if parts else "")


__all__ = ["ReadingTextRenderer"]
