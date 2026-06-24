# ====== Code Summary ======
# CrossReferenceLinker (Axe 4) — resolves intra-document references ("see Figure 3", "cf.
# Article 5", "Annexe A") to the chunk that actually holds that figure/table/section, and records
# the target ids in each chunk's prov["linked_chunk_ids"]. This makes a reference findable even
# when the cited element lives far away in the document.

# ====== Standard Library Imports ======
from __future__ import annotations

import re

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk

# Reference / label grammar: a kind keyword (FR/EN) followed by a number, roman numeral, or
# single letter. Case-insensitive; used both to extract anchors and to find references.
_REF_RE = re.compile(
    r"\b(figures?|fig\.?|tableaux?|tables?|annexes?|annex|appendix|articles?|art\.?"
    r"|sections?|chapitres?|chapters?|parties?|parts?|titres?)\s+"
    r"(\d+(?:\.\d+)*|[IVXLC]{1,6}|[A-Z])\b",
    re.IGNORECASE,
)

# Map each surface keyword to a canonical anchor kind (FR/EN synonyms collapse together).
_KIND_CANON: dict[str, str] = {
    "figure": "figure", "figures": "figure", "fig": "figure", "fig.": "figure",
    "tableau": "table", "tableaux": "table", "table": "table", "tables": "table",
    "annexe": "annexe", "annexes": "annexe", "annex": "annexe", "appendix": "annexe",
    "article": "article", "articles": "article", "art": "article", "art.": "article",
    "section": "section", "sections": "section",
    "chapitre": "chapitre", "chapitres": "chapitre", "chapter": "chapitre", "chapters": "chapitre",
    "partie": "partie", "parties": "partie", "part": "partie", "parts": "partie",
    "titre": "titre", "titres": "titre",
}

# Anchor kinds carried by a FIGURE/TABLE chunk's own caption (vs. heading-path section anchors).
_FIGURE_KINDS = frozenset({"figure", "table"})
_SECTION_KINDS = frozenset({"annexe", "article", "section", "chapitre", "partie", "titre"})


class CrossReferenceLinker(LoggerClass):
    """
    Link chunks that cite a figure/table/section to the chunk holding that element.

    Two passes over the chunk list: build an anchor index ``(kind, number) → chunk_id`` from
    figure/table captions and section breadcrumbs, then attach ``linked_chunk_ids`` to every
    chunk whose text references a known anchor.
    """

    def __init__(self) -> None:
        """Initialize the cross-reference linker."""
        LoggerClass.__init__(self)

    def link(self, chunks: list[Chunk]) -> int:
        """
        Resolve references across the chunk set, mutating ``prov["linked_chunk_ids"]`` in place.

        Args:
            chunks (list[Chunk]): All chunks of a document, in reading order.

        Returns:
            int: Total number of (chunk → target) links recorded.
        """
        # 1. Build the anchor index from captions + section breadcrumbs
        anchors = self._build_anchors(chunks)
        if not anchors:
            return 0

        # 2. Attach links for every chunk that references a known anchor
        n_links = 0
        for chunk in chunks:
            targets = self._resolve_references(chunk, anchors)
            if targets:
                if not isinstance(chunk.prov, dict):
                    chunk.prov = {}
                chunk.prov["linked_chunk_ids"] = targets
                n_links += len(targets)
        self.logger.debug(f"CrossReferenceLinker: anchors={len(anchors)} links={n_links}")
        return n_links

    # ─── Internal ──────────────────────────────────────────────────────────────

    def _build_anchors(self, chunks: list[Chunk]) -> dict[tuple[str, str], str]:
        """Build ``(kind, number) → chunk_id`` from figure/table captions and section paths."""
        anchors: dict[tuple[str, str], str] = {}
        for chunk in chunks:
            # 1. Figure/table chunks: the label lives in their (caption-bearing) text
            if chunk.strategy in _FIGURE_KINDS:
                key = self._first_label(chunk.raw_text, _FIGURE_KINDS)
                if key is not None:
                    anchors.setdefault(key, chunk.id)
            # 2. Any chunk: section labels in the heading breadcrumb (first occurrence wins)
            heading_path = chunk.prov.get("heading_path", "") if isinstance(chunk.prov, dict) else ""
            for key in self._all_labels(heading_path, _SECTION_KINDS):
                anchors.setdefault(key, chunk.id)
        return anchors

    def _resolve_references(self, chunk: Chunk, anchors: dict[tuple[str, str], str]) -> list[str]:
        """Return the sorted unique anchor chunk ids referenced by this chunk (excluding self)."""
        targets: set[str] = set()
        for kind, number in self._all_labels(chunk.raw_text, None):
            target_id = anchors.get((kind, number))
            if target_id and target_id != chunk.id:
                targets.add(target_id)
        return sorted(targets)

    @classmethod
    def _first_label(cls, text: str, kinds: frozenset[str]) -> tuple[str, str] | None:
        """Return the first ``(kind, number)`` label of an allowed kind found in text."""
        for key in cls._all_labels(text, kinds):
            return key
        return None

    @staticmethod
    def _all_labels(text: str, kinds: frozenset[str] | None) -> list[tuple[str, str]]:
        """
        Extract every ``(canonical_kind, normalized_number)`` label from text.

        Args:
            text (str): Text to scan.
            kinds (frozenset[str] | None): Restrict to these canonical kinds, or None for all.

        Returns:
            list[tuple[str, str]]: Labels in order of appearance.
        """
        if not text:
            return []
        out: list[tuple[str, str]] = []
        for match in _REF_RE.finditer(text):
            kind = _KIND_CANON.get(match.group(1).lower())
            if kind is None or (kinds is not None and kind not in kinds):
                continue
            out.append((kind, match.group(2).upper()))
        return out
