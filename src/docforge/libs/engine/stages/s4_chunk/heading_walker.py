# ====== Code Summary ======
# HeadingWalker — static helper that converts an ordered IR block list into traversal items.
# Responsibilities: heading skeleton construction, caption co-location map, atomic-block detection,
# and the main _collect_items walk that produces _Segment / _Special items in reading order.

# ====== Standard Library Imports ======
from __future__ import annotations

import re
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.core.ir.models import Block, BlockType, FigureKind
from libs.core.contracts.pipeline_config import AtomicConfig

# ====== Local Project Imports ======
from .models import _Segment, _Special

# Regex heading candidates are restricted to short, single-line blocks to avoid promoting
# ordinary paragraphs that merely start with a number/keyword.
_MAX_HEADING_CHARS: int = 160


class HeadingWalker:
    """
    Static helper that walks IR blocks and produces ordered traversal items.

    Converts a flat block list into a mix of _Segment (contiguous text under a heading
    path) and _Special (atomic figure/table) items, ready for assembly into chunks.
    """

    logger = loggerplusplus.bind(identifier="HeadingWalker")

    _ALWAYS_SKIP: frozenset[BlockType] = frozenset({BlockType.HEADER_FOOTER})
    _CONTENT_TYPES: frozenset[BlockType] = frozenset(
        {BlockType.PARAGRAPH, BlockType.LIST_ITEM, BlockType.CAPTION, BlockType.CODE, BlockType.FORMULA}
    )
    _FOLDABLE_TYPES: frozenset[BlockType] = frozenset({BlockType.FIGURE, BlockType.TABLE})

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("HeadingWalker is a static-only class and cannot be instantiated.")

    @classmethod
    def caption_map(
        cls,
        blocks: list[Block],
        atomic: AtomicConfig,
        rules: list[tuple[int, re.Pattern]],
    ) -> tuple[set[str], dict[str, list[Block]]]:
        """
        Attach a CAPTION block adjacent to an atomic FIGURE/TABLE to that block.

        Args:
            blocks (list[Block]): All IR blocks in reading order.
            atomic (AtomicConfig): Atomic-block policy (figures/tables/captions).
            rules (list[tuple[int, re.Pattern]]): Compiled heading promotion rules.

        Returns:
            tuple[set[str], dict[str, list[Block]]]: (consumed caption ids, figure/table id →
                its caption blocks).  Empty when caption co-location is disabled.
        """
        # 1. Disabled, or neither figures nor tables are atomic → nothing to attach
        if not atomic.keep_caption_with_figure or not (atomic.figures or atomic.tables):
            return set(), {}

        consumed: set[str] = set()
        caption_of: dict[str, list[Block]] = {}
        for idx, block in enumerate(blocks):
            if not cls.is_atomic_special(block, atomic):
                continue
            # 2. Look at the immediate neighbours for an unclaimed caption
            for nb in (idx - 1, idx + 1):
                if 0 <= nb < len(blocks):
                    cand = blocks[nb]
                    if cand.type == BlockType.CAPTION and cand.id not in consumed:
                        caption_of.setdefault(block.id, []).append(cand)
                        consumed.add(cand.id)
        return consumed, caption_of

    @classmethod
    def collect_items(
        cls,
        blocks: list[Block],
        consumed_caption_ids: set[str],
        atomic: AtomicConfig,
        rules: list[tuple[int, re.Pattern]],
    ) -> list[_Segment | _Special]:
        """
        Walk blocks into ordered items: content sections + atomic figure/table specials.

        Args:
            blocks (list[Block]): All IR blocks in reading order.
            consumed_caption_ids (set[str]): Caption ids already attached to a special block.
            atomic (AtomicConfig): Atomic-block policy.
            rules (list[tuple[int, re.Pattern]]): Compiled heading promotion rules.

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
            if block.type in cls._ALWAYS_SKIP or block.id in consumed_caption_ids:
                continue
            if (
                block.type == BlockType.FIGURE
                and block.figure is not None
                and block.figure.kind == FigureKind.DECORATIVE
            ):
                continue

            # 2. Heading → advance the stack, close the running section
            level = cls.heading_level(block, rules)
            if level is not None:
                flush_segment()
                stack = [(lvl, txt) for lvl, txt in stack if lvl < level]
                stack.append((level, (block.text or "").strip()))
                cur_path = [t for _, t in stack if t.strip()]
                continue

            # 3. Atomic figure/table → flush text, emit a special at this position
            if cls.is_atomic_special(block, atomic):
                flush_segment()
                kind = "figure" if block.type == BlockType.FIGURE else "table"
                items.append(_Special(block=block, path=cur_path[:], kind=kind))
                continue

            # 4. Content (and non-atomic figures/tables folded into the flow) → accumulate
            if block.type in cls._CONTENT_TYPES or block.type in cls._FOLDABLE_TYPES:
                cur_body.append(block)

        flush_segment()
        cls.logger.debug(f"HeadingWalker: collected {len(items)} items from {len(blocks)} blocks")
        return items

    @staticmethod
    def heading_level(block: Block, rules: list[tuple[int, re.Pattern]]) -> int | None:
        """
        Determine a block's heading level, or None if it is not a heading.

        Regex promotion rules win when they match (the configurable structure layer);
        otherwise the parser's own heading level is honored.

        Args:
            block (Block): The IR block to classify.
            rules (list[tuple[int, re.Pattern]]): Compiled (level, pattern) promotion rules.

        Returns:
            int | None: Heading level (1-based) or None if not a heading.
        """
        text = (block.text or "").strip()
        # 1. Regex rules apply to short single-line text (heading-shaped candidates)
        if text and "\n" not in text and len(text) <= _MAX_HEADING_CHARS:
            for level, rx in rules:
                if rx.search(text):
                    return level
        # 2. Fall back to the parser's heading classification
        if block.type == BlockType.HEADING:
            return block.level or 1
        return None

    @staticmethod
    def is_atomic_special(block: Block, atomic: AtomicConfig) -> bool:
        """
        Return True for a non-decorative FIGURE/TABLE that the atomic policy keeps as its own chunk.

        Args:
            block (Block): The IR block to test.
            atomic (AtomicConfig): Atomic-block policy.

        Returns:
            bool: True if the block should be emitted as a standalone special chunk.
        """
        if block.type == BlockType.FIGURE:
            if block.figure is not None and block.figure.kind == FigureKind.DECORATIVE:
                return False
            return atomic.figures
        if block.type == BlockType.TABLE:
            return atomic.tables
        return False
