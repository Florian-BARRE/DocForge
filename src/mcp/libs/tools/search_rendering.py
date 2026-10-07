# ====== Code Summary ======
# Renders a SearchResponse as LLM-ready text: one citation line + the chunk text per hit, so an agent
# reads results directly instead of parsing (and paying tokens for) a JSON envelope. Geometry is
# never rendered here - a client that wants it asks for format="json" with the geometry fields.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk.models import ChunkBrowseResponse, SearchHit, SearchResponse

# ====== Local Project Imports ======
from ..compact_json import compact_json

# Hit fields an agent needs to read and cite a result; identity (chunk_id/document_id) always
# comes back from the API on top of these. Geometry (bbox/block_locations) is deliberately absent.
AGENT_RETURN_FIELDS = [
    "text",
    "document_title",
    "page_number",
    "heading_path",
    "score",
    "metadata",
]

# Browse has no ranking, so no score.
BROWSE_RETURN_FIELDS = [f for f in AGENT_RETURN_FIELDS if f != "score"]

_PART_SEPARATOR = " | "
_HEADING_SEPARATOR = " > "
# debug_info keys that are always-present bookkeeping, not a sign the run degraded.
_ROUTINE_DEBUG_KEYS = frozenset({"hit_count", "grouping"})


class SearchTextRenderer:
    """Formats a `SearchResponse` as compact, citation-first plain text."""

    def render(self, response: SearchResponse) -> str:
        """
        Render the whole response.

        Args:
            response (SearchResponse): The search result from the SDK.

        Returns:
            str: A header line, one block per hit, then one `Hint:` line per hint.
        """
        # 1. Header: hit count + query (+ a debug note only when the run reported non-routine diagnostics)
        header = f'{len(response.hits)} hits for "{response.query}"'
        notable = {
            k: v for k, v in (response.debug_info or {}).items() if k not in _ROUTINE_DEBUG_KEYS
        }
        if notable:
            header += f" (debug: {compact_json(notable)})"

        # 2. One block per hit, in rank order, then the filter hints (if any)
        lines = [header]
        lines.extend(self._render_hit(rank, hit) for rank, hit in enumerate(response.hits, 1))
        lines.extend(f"Hint: {hint.message}" for hint in response.hints)
        return "\n".join(lines)

    def render_browse(self, page: ChunkBrowseResponse) -> str:
        """
        Render one browse page.

        Args:
            page (ChunkBrowseResponse): The browse page from the SDK.

        Returns:
            str: One block per chunk, then the continuation line and any `Hint:` lines.
        """
        lines = [f"{len(page.chunks)} chunks"]
        lines.extend(self._render_hit(rank, hit) for rank, hit in enumerate(page.chunks, 1))
        lines.append(f"next_cursor: {page.next_cursor}" if page.next_cursor else "end of results")
        lines.extend(f"Hint: {hint.message}" for hint in page.hints)
        return "\n".join(lines)

    def _render_hit(self, rank: int, hit: SearchHit) -> str:
        """Render one hit: citation line, optional metadata line, then the text."""
        sent = hit.model_fields_set
        # 1. Citation line: only the parts the server actually returned
        parts: list[str] = []
        if "document_title" in sent or "filename" in sent:
            parts.append(hit.document_title or hit.filename or "(untitled)")
        if hit.page_number is not None:
            parts.append(f"p.{hit.page_number}")
        if hit.heading_path:
            parts.append(_HEADING_SEPARATOR.join(hit.heading_path))
        if "score" in sent:
            parts.append(f"score {hit.score:.2f}")
        if hit.fusion_score is not None or hit.rerank_score is not None:
            fusion = "-" if hit.fusion_score is None else f"{hit.fusion_score:.3f}"
            rerank = "-" if hit.rerank_score is None else f"{hit.rerank_score:.3f}"
            parts.append(f"fusion {fusion} / rerank {rerank}")
        parts.append(f"doc {hit.document_id}")
        parts.append(f"chunk {hit.chunk_id}")
        block = [f"[{rank}] {_PART_SEPARATOR.join(parts)}"]

        # 2. Metadata as a compact k=v line, then the chunk text
        # Only non-null values are rendered — and no empty "meta:" line when none remain.
        meta_pairs = [
            f"{k}={self._format_value(v)}" for k, v in (hit.metadata or {}).items() if v is not None
        ]
        if meta_pairs:
            block.append("meta: " + "; ".join(meta_pairs))
        if "text" in sent:
            block.append(hit.text)
        return "\n".join(block)

    @staticmethod
    def _format_value(value: Any) -> str:
        """Render a metadata value; lists are comma-joined."""
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)


__all__ = ["AGENT_RETURN_FIELDS", "BROWSE_RETURN_FIELDS", "SearchTextRenderer"]
