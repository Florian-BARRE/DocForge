# ====== Code Summary ======
# S4 — Heading-hierarchy-aware chunking stage (orchestrator).
# The heading skeleton (parser headings + configurable regex rules) is always built first —
# that is the structure recovered from our enriched blocks. How an oversize section is cut is a
# pluggable, parameterized method (token_budget / semantic / sentence_window). Special blocks are
# kept atomic (tables, figures, formulas) with adjacent captions co-located. In hierarchical mode
# each divided section also yields a parent chunk over its children. A final cross-reference pass
# links chunks that cite a figure/table/article to the chunk that holds it.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import itertools
import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from ir.chunk import Chunk
from ir.models import Block, BlockType, DocumentIR, FigureKind
from pipeline.pipeline_config import AtomicConfig

# ====== Local Project Imports ======
from .chunking import (
    ChunkingHelpers,
    CrossReferenceLinker,
    SectionSplitter,
    TokenBudgetSplitter,
)

# Regex heading candidates are restricted to short, single-line blocks to avoid promoting
# ordinary paragraphs that merely start with a number/keyword.
_MAX_HEADING_CHARS: int = 160


@dataclass(slots=True)
class _Segment:
    """A contiguous run of content blocks under a single heading path."""

    path: list[str]          # heading texts from root → this section
    blocks: list[Block]      # content blocks (no headings) belonging to the section


@dataclass(slots=True)
class _Special:
    """An atomic figure/table emitted as its own chunk at its position in reading order."""

    block: Block             # the FIGURE or TABLE block
    path: list[str]          # active heading breadcrumb at this position
    kind: str                # "figure" or "table"


@dataclass(slots=True)
class S4Result:
    """
    Output of the S4 heading-aware chunking stage.

    Attributes:
        chunks (list[Chunk]): Chunks with raw_text + prov.heading_path set; embed_text empty.
        config_hash (str): blake2b of the chunking configuration (Merkle fingerprint input).
        n_text_chunks (int): Number of text chunks (packed / split sections, and children).
        n_figure_chunks (int): Number of figure chunks.
        n_table_chunks (int): Number of table chunks.
        n_parent_chunks (int): Number of hierarchical parent (section) chunks.
    """

    chunks: list[Chunk]
    config_hash: str
    n_text_chunks: int
    n_figure_chunks: int
    n_table_chunks: int
    n_parent_chunks: int = 0


class S4ChunkStage(LoggerClass):
    """
    S4 — Heading-hierarchy-aware chunker.

    Pipeline per document:
    1. Build the heading skeleton (parser headings + regex promotion rules) and group content
       into sections; emit atomic figures/tables (with co-located captions) at their position.
    2. Flat mode: pack small sibling sections together up to the token budget and split oversize
       sections with the configured split method.  Hierarchical mode: each divided section yields
       a parent chunk over its children (parent_id set).
    3. Link cross-references (see Figure 3 / Article 5) to the chunks that hold them.
    """

    _ALWAYS_SKIP: frozenset[BlockType] = frozenset({BlockType.HEADER_FOOTER})
    _CONTENT_TYPES: frozenset[BlockType] = frozenset(
        {BlockType.PARAGRAPH, BlockType.LIST_ITEM, BlockType.CAPTION, BlockType.CODE, BlockType.FORMULA}
    )
    _FOLDABLE_TYPES: frozenset[BlockType] = frozenset({BlockType.FIGURE, BlockType.TABLE})
    _PARENT_STRATEGY: str = "section_parent"

    def __init__(
        self,
        *,
        splitter: SectionSplitter | None = None,
        heading_rules: list[Any] | None = None,
        reinject_breadcrumb: bool = True,
        merge_short_sections: bool = True,
        atomic: AtomicConfig | None = None,
        cross_references: bool = True,
        hierarchical: bool = False,
    ) -> None:
        """
        Initialize the chunking stage.

        Args:
            splitter (SectionSplitter | None): Intra-section split method. None → a default
                TokenBudgetSplitter with its own defaults.
            heading_rules (list | None): Ordered HeadingRule-like objects (``.level``, ``.pattern``)
                promoting text to headings.  None → parser headings only.
            reinject_breadcrumb (bool): Record the section breadcrumb on each chunk so split
                sub-chunks remain section-aware (consumed by S5 for embed_text).
            merge_short_sections (bool): Pack small sibling sections together (flat mode only).
            atomic (AtomicConfig | None): Atomic-block policy (tables/figures/formulas/captions).
            cross_references (bool): Run the cross-reference linking pass.
            hierarchical (bool): Emit a parent chunk per divided section over its children.
        """
        LoggerClass.__init__(self)
        self._splitter: SectionSplitter = splitter or TokenBudgetSplitter()
        self._reinject = reinject_breadcrumb
        self._merge_short = merge_short_sections
        self._atomic = atomic or AtomicConfig()
        self._cross_references = cross_references
        self._hierarchical = hierarchical
        self._max_tokens = self._splitter.max_tokens
        # Compile (level, regex) rules once; skip patterns that fail to compile.
        self._rules: list[tuple[int, re.Pattern]] = []
        for rule in heading_rules or []:
            try:
                self._rules.append((int(rule.level), re.compile(rule.pattern)))
            except (re.error, AttributeError, ValueError):
                self.logger.warning(f"S4: skipping invalid heading rule {rule!r}")
        self._config_hash = self._compute_config_hash(heading_rules or [])

    def params_for_fingerprint(self) -> dict[str, Any]:
        """Return chunking parameters for the S4 Merkle fingerprint."""
        return self._config_dict([(lvl, rx.pattern) for lvl, rx in self._rules])

    async def run(self, ir: DocumentIR) -> S4Result:
        """
        Chunk all blocks in the enriched DocumentIR using heading-hierarchy awareness.

        Args:
            ir (DocumentIR): Enriched DocumentIR from S2.

        Returns:
            S4Result: Chunks in reading order, each tagged with its section breadcrumb.
        """
        self.logger.info(
            f"S4 started: doc_id={ir.doc_id} blocks={len(ir.blocks)} "
            f"method={self._splitter.name} hierarchical={self._hierarchical} rules={len(self._rules)}"
        )

        # 1. Map captions onto their atomic figure/table, then collect ordered items
        consumed_caption_ids, caption_of = self._caption_map(ir.blocks)
        items = self._collect_items(ir.blocks, consumed_caption_ids)

        # 2. Deterministic ordinal stream for stable, collision-free chunk ids
        counter = itertools.count()

        # 3. Build chunks (flat packing vs. hierarchical parent/children)
        if self._hierarchical:
            chunks = await self._process_hierarchical(items, ir.doc_id, caption_of, counter)
        else:
            chunks = await self._process_flat(items, ir.doc_id, caption_of, counter)

        # 4. Cross-reference linking (Axe 4) — best-effort, mutates prov in place
        if self._cross_references:
            CrossReferenceLinker().link(chunks)

        # 5. Tally counts by chunk kind
        n_figure = sum(1 for c in chunks if c.strategy == "figure")
        n_table = sum(1 for c in chunks if c.strategy == "table")
        n_parent = sum(1 for c in chunks if c.strategy == self._PARENT_STRATEGY)
        n_text = len(chunks) - n_figure - n_table - n_parent

        result = S4Result(
            chunks=chunks,
            config_hash=self._config_hash,
            n_text_chunks=n_text,
            n_figure_chunks=n_figure,
            n_table_chunks=n_table,
            n_parent_chunks=n_parent,
        )
        self.logger.info(
            f"S4 done: doc_id={ir.doc_id} chunks={len(chunks)} "
            f"(text={n_text} figure={n_figure} table={n_table} parent={n_parent})"
        )
        return result

    # ─── Caption co-location (Axe 3) ───────────────────────────────────────────

    def _caption_map(self, blocks: list[Block]) -> tuple[set[str], dict[str, list[Block]]]:
        """
        Attach a CAPTION block adjacent to an atomic FIGURE/TABLE to that block.

        Args:
            blocks (list[Block]): All IR blocks in reading order.

        Returns:
            tuple[set[str], dict[str, list[Block]]]: (consumed caption ids, figure/table id →
                its caption blocks).  Empty when caption co-location is disabled.
        """
        # 1. Disabled, or neither figures nor tables are atomic → nothing to attach
        if not self._atomic.keep_caption_with_figure or not (self._atomic.figures or self._atomic.tables):
            return set(), {}

        consumed: set[str] = set()
        caption_of: dict[str, list[Block]] = {}
        for idx, block in enumerate(blocks):
            if not self._is_atomic_special(block):
                continue
            # 2. Look at the immediate neighbours for an unclaimed caption
            for nb in (idx - 1, idx + 1):
                if 0 <= nb < len(blocks):
                    cand = blocks[nb]
                    if cand.type == BlockType.CAPTION and cand.id not in consumed:
                        caption_of.setdefault(block.id, []).append(cand)
                        consumed.add(cand.id)
        return consumed, caption_of

    # ─── Item collection (heading skeleton) ────────────────────────────────────

    def _collect_items(
        self, blocks: list[Block], consumed_caption_ids: set[str]
    ) -> list[_Segment | _Special]:
        """
        Walk blocks into ordered items: content sections + atomic figure/table specials.

        Args:
            blocks (list[Block]): All IR blocks in reading order.
            consumed_caption_ids (set[str]): Caption ids already attached to a special block.

        Returns:
            list[_Segment | _Special]: Items in reading order.
        """
        items: list[_Segment | _Special] = []
        stack: list[tuple[int, str]] = []
        cur_path: list[str] = []
        cur_body: list[Block] = []

        def flush_segment() -> None:
            # Buffer the current section body as a segment (skip empty → no title-only chunk).
            if cur_body:
                items.append(_Segment(path=cur_path[:], blocks=cur_body[:]))
                cur_body.clear()

        for block in blocks:
            # 1. Drop header/footer, decorative figures, and consumed captions
            if block.type in self._ALWAYS_SKIP or block.id in consumed_caption_ids:
                continue
            if (
                block.type == BlockType.FIGURE
                and block.figure is not None
                and block.figure.kind == FigureKind.DECORATIVE
            ):
                continue

            # 2. Heading → advance the stack, close the running section
            level = self._heading_level(block)
            if level is not None:
                flush_segment()
                stack = [(lvl, txt) for lvl, txt in stack if lvl < level]
                stack.append((level, (block.text or "").strip()))
                cur_path = [t for _, t in stack if t.strip()]
                continue

            # 3. Atomic figure/table → flush text, emit a special at this position
            if self._is_atomic_special(block):
                flush_segment()
                kind = "figure" if block.type == BlockType.FIGURE else "table"
                items.append(_Special(block=block, path=cur_path[:], kind=kind))
                continue

            # 4. Content (and non-atomic figures/tables folded into the flow) → accumulate
            if block.type in self._CONTENT_TYPES or block.type in self._FOLDABLE_TYPES:
                cur_body.append(block)

        flush_segment()
        return items

    # ─── Flat processing (sibling packing + oversize split) ────────────────────

    async def _process_flat(
        self,
        items: list[_Segment | _Special],
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
    ) -> list[Chunk]:
        """Pack small sibling sections, split oversize ones; specials emitted inline."""
        chunks: list[Chunk] = []
        pending: list[_Segment] = []
        for item in items:
            if isinstance(item, _Segment):
                pending.append(item)
                continue
            # A special interrupts the text flow → flush pending sections first
            chunks.extend(await self._pack_segments(pending, doc_id, counter))
            pending = []
            chunks.append(self._emit_special(item, doc_id, caption_of, counter))
        chunks.extend(await self._pack_segments(pending, doc_id, counter))
        return chunks

    async def _pack_segments(
        self, segments: list[_Segment], doc_id: str, counter: Iterator[int]
    ) -> list[Chunk]:
        """
        Pack consecutive small sibling segments into chunks; split oversize segments.

        Greedy: accumulate segments while the running token total fits ``max_tokens``.  A single
        segment exceeding the budget is split via the configured method.  Every emitted chunk
        records the longest-common heading path of its segments as the breadcrumb.
        """
        chunks: list[Chunk] = []
        buffer: list[_Segment] = []
        buf_tokens = 0

        for seg in segments:
            seg_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in seg.blocks)

            # 1. Oversize section → flush buffer, then split it on its own
            if seg_tokens > self._max_tokens:
                if buffer:
                    chunks.append(self._segments_to_chunk(buffer, doc_id, counter))
                    buffer, buf_tokens = [], 0
                chunks.extend(await self._split_section_to_chunks(seg, doc_id, counter))
                continue

            # 2. Packing this segment would overflow (or merging is off) → flush first
            if buffer and (not self._merge_short or buf_tokens + seg_tokens > self._max_tokens):
                chunks.append(self._segments_to_chunk(buffer, doc_id, counter))
                buffer, buf_tokens = [], 0

            buffer.append(seg)
            buf_tokens += seg_tokens

        if buffer:
            chunks.append(self._segments_to_chunk(buffer, doc_id, counter))
        return chunks

    def _segments_to_chunk(
        self, segments: list[_Segment], doc_id: str, counter: Iterator[int]
    ) -> Chunk:
        """
        Merge one or more sibling segments into a single chunk.

        The chunk breadcrumb is the longest common heading path; any deeper per-segment heading
        is rendered inline (so structure survives) — never the common prefix, so the breadcrumb
        is never duplicated inside the body.
        """
        common = ChunkingHelpers.longest_common_prefix([s.path for s in segments])
        common_depth = len(common)

        parts: list[str] = []
        block_ids: list[str] = []
        all_blocks: list[Block] = []
        for seg in segments:
            # Render heading levels deeper than the shared breadcrumb as inline headings
            for i, title in enumerate(seg.path[common_depth:]):
                if title.strip():
                    parts.append(f"{'#' * (common_depth + i + 1)} {title}")
            body = ChunkingHelpers.blocks_to_text(seg.blocks)
            if body:
                parts.append(body)
            block_ids.extend(b.id for b in seg.blocks)
            all_blocks.extend(seg.blocks)

        raw_text = "\n\n".join(p for p in parts if p.strip())
        return self._make_chunk(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=self._splitter.name,
            prov=ChunkingHelpers.aggregate_prov(all_blocks, " > ".join(common)),
            counter=counter,
        )

    async def _split_section_to_chunks(
        self, seg: _Segment, doc_id: str, counter: Iterator[int]
    ) -> list[Chunk]:
        """Split one oversize section via the configured method, all sharing its breadcrumb."""
        pieces = await self._splitter.split_section(seg.blocks)
        breadcrumb = " > ".join(seg.path)
        bmap = {b.id: b for b in seg.blocks}
        chunks: list[Chunk] = []
        for piece in pieces:
            blocks = [bmap[bid] for bid in piece.block_ids if bid in bmap]
            chunks.append(self._make_chunk(
                block_ids=piece.block_ids,
                raw_text=piece.text,
                doc_id=doc_id,
                strategy=self._splitter.name,
                prov=ChunkingHelpers.aggregate_prov(blocks, breadcrumb),
                counter=counter,
            ))
        return chunks

    # ─── Hierarchical processing (parent + children) ───────────────────────────

    async def _process_hierarchical(
        self,
        items: list[_Segment | _Special],
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
    ) -> list[Chunk]:
        """Each divided section yields a parent over its children; specials stay flat."""
        chunks: list[Chunk] = []
        for item in items:
            if isinstance(item, _Special):
                chunks.append(self._emit_special(item, doc_id, caption_of, counter))
                continue
            chunks.extend(await self._section_with_parent(item, doc_id, counter))
        return chunks

    async def _section_with_parent(
        self, seg: _Segment, doc_id: str, counter: Iterator[int]
    ) -> list[Chunk]:
        """Emit a flat chunk when a section fits/cannot divide, else a parent + its children."""
        breadcrumb = " > ".join(seg.path)
        seg_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in seg.blocks)

        # 1. Fits in the budget → one flat chunk (is its own context)
        if seg_tokens <= self._max_tokens:
            return [self._flat_section_chunk(seg, doc_id, breadcrumb, counter)]

        # 2. Oversize → split; a single piece means the splitter could not divide it
        pieces = await self._splitter.split_section(seg.blocks)
        if len(pieces) <= 1:
            return [self._flat_section_chunk(seg, doc_id, breadcrumb, counter)]

        # 3. Parent (full section) over its children (the pieces)
        parent = self._make_chunk(
            block_ids=[b.id for b in seg.blocks],
            raw_text=ChunkingHelpers.blocks_to_text(seg.blocks),
            doc_id=doc_id,
            strategy=self._PARENT_STRATEGY,
            prov=ChunkingHelpers.aggregate_prov(seg.blocks, breadcrumb),
            counter=counter,
        )
        chunks: list[Chunk] = [parent]
        bmap = {b.id: b for b in seg.blocks}
        for piece in pieces:
            blocks = [bmap[bid] for bid in piece.block_ids if bid in bmap]
            chunks.append(self._make_chunk(
                block_ids=piece.block_ids,
                raw_text=piece.text,
                doc_id=doc_id,
                strategy=self._splitter.name,
                prov=ChunkingHelpers.aggregate_prov(blocks, breadcrumb),
                counter=counter,
                parent_id=parent.id,
            ))
        return chunks

    def _flat_section_chunk(
        self, seg: _Segment, doc_id: str, breadcrumb: str, counter: Iterator[int]
    ) -> Chunk:
        """Build a single flat chunk for an undivided section."""
        return self._make_chunk(
            block_ids=[b.id for b in seg.blocks],
            raw_text=ChunkingHelpers.blocks_to_text(seg.blocks),
            doc_id=doc_id,
            strategy=self._splitter.name,
            prov=ChunkingHelpers.aggregate_prov(seg.blocks, breadcrumb),
            counter=counter,
        )

    # ─── Special-block chunk emitter (Axe 3) ───────────────────────────────────

    def _emit_special(
        self,
        item: _Special,
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
    ) -> Chunk:
        """Emit a single chunk for an atomic FIGURE/TABLE, with its caption co-located."""
        block = item.block
        captions = caption_of.get(block.id, [])
        breadcrumb = " > ".join(item.path)

        # Caption first so the label ("Figure 3") leads the text (helps cross-ref anchoring)
        body = ChunkingHelpers.figure_to_text(block) if item.kind == "figure" else ChunkingHelpers.table_to_text(block)
        caption_text = "\n".join(c.text or "" for c in captions).strip()
        raw_text = "\n\n".join(p for p in (caption_text, body) if p.strip())

        block_ids = [block.id] + [c.id for c in captions]
        return self._make_chunk(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=item.kind,
            prov=ChunkingHelpers.aggregate_prov([block, *captions], breadcrumb),
            counter=counter,
        )

    # ─── Chunk construction ────────────────────────────────────────────────────

    def _make_chunk(
        self,
        block_ids: list[str],
        raw_text: str,
        doc_id: str,
        strategy: str,
        prov: dict[str, Any],
        counter: Iterator[int],
        parent_id: str | None = None,
    ) -> Chunk:
        """Build a Chunk with a deterministic UUID derived from its content identity + ordinal."""
        ordinal = next(counter)
        return Chunk(
            id=ChunkingHelpers.stable_chunk_uuid(doc_id, block_ids, self._config_hash, ordinal),
            document_id=doc_id,
            config_hash=self._config_hash,
            block_ids=block_ids,
            raw_text=raw_text,
            embed_text="",          # Filled by S5 from prov.heading_path + body
            token_count=ChunkingHelpers.estimate_tokens_text(raw_text),
            strategy=strategy,
            prov=prov,
            parent_id=parent_id,
        )

    # ─── Heading detection ─────────────────────────────────────────────────────

    def _heading_level(self, block: Block) -> int | None:
        """
        Determine a block's heading level, or None if it is not a heading.

        Regex promotion rules win when they match (the configurable structure layer);
        otherwise the parser's own heading level is honored.
        """
        text = (block.text or "").strip()
        # 1. Regex rules apply to short single-line text (heading-shaped candidates)
        if text and "\n" not in text and len(text) <= _MAX_HEADING_CHARS:
            for level, rx in self._rules:
                if rx.search(text):
                    return level
        # 2. Fall back to the parser's heading classification
        if block.type == BlockType.HEADING:
            return block.level or 1
        return None

    # ─── Config hashing ────────────────────────────────────────────────────────

    def _is_atomic_special(self, block: Block) -> bool:
        """True for a non-decorative FIGURE/TABLE that the atomic policy keeps as its own chunk."""
        if block.type == BlockType.FIGURE:
            if block.figure is not None and block.figure.kind == FigureKind.DECORATIVE:
                return False
            return self._atomic.figures
        if block.type == BlockType.TABLE:
            return self._atomic.tables
        return False

    def _config_dict(self, heading_rules: list[Any]) -> dict[str, Any]:
        """Assemble the full configuration dict used for the deterministic hash + fingerprint."""
        # heading_rules may be (level, pattern) tuples (from compiled rules) or rule-like objects.
        rules: list[dict[str, Any]] = []
        for r in heading_rules:
            if isinstance(r, tuple):
                rules.append({"level": r[0], "pattern": r[1]})
            else:
                rules.append({"level": getattr(r, "level", None), "pattern": getattr(r, "pattern", None)})
        return {
            "split_method": self._splitter.signature(),
            "reinject_breadcrumb": self._reinject,
            "merge_short_sections": self._merge_short,
            "hierarchical": self._hierarchical,
            "cross_references": self._cross_references,
            "atomic": self._atomic.model_dump(),
            "heading_rules": rules,
        }

    def _compute_config_hash(self, heading_rules: list[Any]) -> str:
        """Compute a deterministic hash of the chunking configuration."""
        config_str = json.dumps(self._config_dict(heading_rules), sort_keys=True)
        return hashlib.blake2b(config_str.encode(), digest_size=16).hexdigest()
