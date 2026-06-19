# ====== Code Summary ======
# ChunkAssembler — static helper that converts traversal items (_Segment / _Special) into Chunk
# objects.  Covers: flat greedy packing, oversize section splitting, hierarchical parent/child
# emission, special-block (figure/table) chunk construction, and the shared chunk factory.
# All methods are pure (no mutable state) and delegate to the configured SectionSplitter.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.core.ir.chunk import Chunk
from libs.core.ir.models import Block

from ..chunking import ChunkingHelpers, SectionSplitter

# ====== Local Project Imports ======
from .models import _PARENT_STRATEGY, _Segment, _Special


class ChunkAssembler:
    """
    Static helper that assembles Chunk objects from structured traversal items.

    Provides flat packing, hierarchical parent/child mode, special-block emission,
    and the shared chunk factory used by all assembly paths.
    """

    logger = loggerplusplus.bind(identifier="ChunkAssembler")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkAssembler is a static-only class and cannot be instantiated.")

    # ─── Flat processing (sibling packing + oversize split) ────────────────────

    @classmethod
    async def process_flat(
        cls,
        items: list[_Segment | _Special],
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
        splitter: SectionSplitter,
        merge_short: bool,
        config_hash: str,
    ) -> list[Chunk]:
        """
        Pack small sibling sections together; split oversize ones; emit specials inline.

        Args:
            items (list[_Segment | _Special]): Ordered traversal items from HeadingWalker.
            doc_id (str): Document identifier to stamp on every chunk.
            caption_of (dict[str, list[Block]]): Caption blocks keyed by their atomic block id.
            counter (Iterator[int]): Deterministic ordinal stream for stable chunk ids.
            splitter (SectionSplitter): Configured intra-section split method.
            merge_short (bool): Whether to pack small sibling segments together.
            config_hash (str): Chunking configuration hash for chunk id derivation.

        Returns:
            list[Chunk]: Assembled chunks in reading order.
        """
        chunks: list[Chunk] = []
        pending: list[_Segment] = []
        for item in items:
            if isinstance(item, _Segment):
                pending.append(item)
                continue
            # A special interrupts the text flow → flush pending sections first
            chunks.extend(
                await cls._pack_segments(pending, doc_id, counter, splitter, merge_short, config_hash)
            )
            pending = []
            chunks.append(cls._emit_special(item, doc_id, caption_of, counter, config_hash))
        chunks.extend(
            await cls._pack_segments(pending, doc_id, counter, splitter, merge_short, config_hash)
        )
        cls.logger.debug(f"ChunkAssembler flat: assembled {len(chunks)} chunks for doc_id={doc_id!r}")
        return chunks

    @classmethod
    async def _pack_segments(
        cls,
        segments: list[_Segment],
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        merge_short: bool,
        config_hash: str,
    ) -> list[Chunk]:
        """
        Pack consecutive small sibling segments into chunks; split oversize segments.

        Greedy: accumulate segments while the running token total fits max_tokens.  A single
        segment exceeding the budget is split via the configured method.  Every emitted chunk
        records the longest-common heading path of its segments as the breadcrumb.

        Args:
            segments (list[_Segment]): Sibling sections to pack.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Split method for oversize sections.
            merge_short (bool): Pack small siblings when True.
            config_hash (str): Configuration hash.

        Returns:
            list[Chunk]: Packed and/or split chunks.
        """
        max_tokens = splitter.max_tokens
        chunks: list[Chunk] = []
        buffer: list[_Segment] = []
        buf_tokens = 0

        for seg in segments:
            seg_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in seg.blocks)

            # 1. Oversize section → flush buffer, then split it on its own
            if seg_tokens > max_tokens:
                if buffer:
                    chunks.append(cls._segments_to_chunk(buffer, doc_id, counter, splitter, config_hash))
                    buffer, buf_tokens = [], 0
                chunks.extend(
                    await cls._split_section_to_chunks(seg, doc_id, counter, splitter, config_hash)
                )
                continue

            # 2. Packing this segment would overflow (or merging is off) → flush first
            if buffer and (not merge_short or buf_tokens + seg_tokens > max_tokens):
                chunks.append(cls._segments_to_chunk(buffer, doc_id, counter, splitter, config_hash))
                buffer, buf_tokens = [], 0

            buffer.append(seg)
            buf_tokens += seg_tokens

        if buffer:
            chunks.append(cls._segments_to_chunk(buffer, doc_id, counter, splitter, config_hash))
        return chunks

    @classmethod
    def _segments_to_chunk(
        cls,
        segments: list[_Segment],
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
    ) -> Chunk:
        """
        Merge one or more sibling segments into a single chunk.

        The chunk breadcrumb is the longest common heading path; any deeper per-segment heading
        is rendered inline (so structure survives) — never the common prefix, so the breadcrumb
        is never duplicated inside the body.

        Args:
            segments (list[_Segment]): Segments to merge.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Used for its name as the strategy label.
            config_hash (str): Configuration hash.

        Returns:
            Chunk: Merged chunk with the common breadcrumb set on prov.
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
        return cls._make_chunk(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=splitter.name,
            prov=ChunkingHelpers.aggregate_prov(all_blocks, " > ".join(common)),
            counter=counter,
            config_hash=config_hash,
        )

    @classmethod
    async def _split_section_to_chunks(
        cls,
        seg: _Segment,
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
    ) -> list[Chunk]:
        """
        Split one oversize section via the configured method, all sharing its breadcrumb.

        Args:
            seg (_Segment): Section whose token count exceeds max_tokens.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): The split method to invoke.
            config_hash (str): Configuration hash.

        Returns:
            list[Chunk]: Sub-chunks produced by the splitter.
        """
        pieces = await splitter.split_section(seg.blocks)
        breadcrumb = " > ".join(seg.path)
        bmap = {b.id: b for b in seg.blocks}
        chunks: list[Chunk] = []
        for piece in pieces:
            blocks = [bmap[bid] for bid in piece.block_ids if bid in bmap]
            chunks.append(cls._make_chunk(
                block_ids=piece.block_ids,
                raw_text=piece.text,
                doc_id=doc_id,
                strategy=splitter.name,
                prov=ChunkingHelpers.aggregate_prov(blocks, breadcrumb),
                counter=counter,
                config_hash=config_hash,
            ))
        return chunks

    # ─── Hierarchical processing (parent + children) ───────────────────────────

    @classmethod
    async def process_hierarchical(
        cls,
        items: list[_Segment | _Special],
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
    ) -> list[Chunk]:
        """
        Emit parent + children for every divided section; specials stay flat.

        Args:
            items (list[_Segment | _Special]): Ordered traversal items.
            doc_id (str): Document identifier.
            caption_of (dict[str, list[Block]]): Caption blocks keyed by atomic block id.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Configured split method.
            config_hash (str): Configuration hash.

        Returns:
            list[Chunk]: Chunks in reading order (parent immediately precedes its children).
        """
        chunks: list[Chunk] = []
        for item in items:
            if isinstance(item, _Special):
                chunks.append(cls._emit_special(item, doc_id, caption_of, counter, config_hash))
                continue
            chunks.extend(
                await cls._section_with_parent(item, doc_id, counter, splitter, config_hash)
            )
        return chunks

    @classmethod
    async def _section_with_parent(
        cls,
        seg: _Segment,
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
    ) -> list[Chunk]:
        """
        Emit a flat chunk when a section fits/cannot divide, else a parent + its children.

        Args:
            seg (_Segment): The section to process.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Split method.
            config_hash (str): Configuration hash.

        Returns:
            list[Chunk]: One flat chunk or [parent, child1, child2, ...].
        """
        breadcrumb = " > ".join(seg.path)
        seg_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in seg.blocks)

        # 1. Fits in the budget → one flat chunk (is its own context)
        if seg_tokens <= splitter.max_tokens:
            return [cls._flat_section_chunk(seg, doc_id, breadcrumb, counter, splitter, config_hash)]

        # 2. Oversize → split; a single piece means the splitter could not divide it
        pieces = await splitter.split_section(seg.blocks)
        if len(pieces) <= 1:
            return [cls._flat_section_chunk(seg, doc_id, breadcrumb, counter, splitter, config_hash)]

        # 3. Parent (full section) over its children (the pieces)
        parent = cls._make_chunk(
            block_ids=[b.id for b in seg.blocks],
            raw_text=ChunkingHelpers.blocks_to_text(seg.blocks),
            doc_id=doc_id,
            strategy=_PARENT_STRATEGY,
            prov=ChunkingHelpers.aggregate_prov(seg.blocks, breadcrumb),
            counter=counter,
            config_hash=config_hash,
        )
        chunks: list[Chunk] = [parent]
        bmap = {b.id: b for b in seg.blocks}
        for piece in pieces:
            blocks = [bmap[bid] for bid in piece.block_ids if bid in bmap]
            chunks.append(cls._make_chunk(
                block_ids=piece.block_ids,
                raw_text=piece.text,
                doc_id=doc_id,
                strategy=splitter.name,
                prov=ChunkingHelpers.aggregate_prov(blocks, breadcrumb),
                counter=counter,
                config_hash=config_hash,
                parent_id=parent.id,
            ))
        return chunks

    @classmethod
    def _flat_section_chunk(
        cls,
        seg: _Segment,
        doc_id: str,
        breadcrumb: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
    ) -> Chunk:
        """
        Build a single flat chunk for an undivided section.

        Args:
            seg (_Segment): The undivided section.
            doc_id (str): Document identifier.
            breadcrumb (str): Pre-formatted heading breadcrumb string.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Used for its name as the strategy label.
            config_hash (str): Configuration hash.

        Returns:
            Chunk: A single flat chunk for the section.
        """
        return cls._make_chunk(
            block_ids=[b.id for b in seg.blocks],
            raw_text=ChunkingHelpers.blocks_to_text(seg.blocks),
            doc_id=doc_id,
            strategy=splitter.name,
            prov=ChunkingHelpers.aggregate_prov(seg.blocks, breadcrumb),
            counter=counter,
            config_hash=config_hash,
        )

    # ─── Special-block chunk emitter (Axe 3) ───────────────────────────────────

    @classmethod
    def _emit_special(
        cls,
        item: _Special,
        doc_id: str,
        caption_of: dict[str, list[Block]],
        counter: Iterator[int],
        config_hash: str,
    ) -> Chunk:
        """
        Emit a single chunk for an atomic FIGURE/TABLE, with its caption co-located.

        Args:
            item (_Special): The atomic special item.
            doc_id (str): Document identifier.
            caption_of (dict[str, list[Block]]): Caption blocks keyed by block id.
            counter (Iterator[int]): Ordinal stream.
            config_hash (str): Configuration hash.

        Returns:
            Chunk: A figure or table chunk, optionally prefixed with its caption.
        """
        block = item.block
        captions = caption_of.get(block.id, [])
        breadcrumb = " > ".join(item.path)

        # Caption first so the label ("Figure 3") leads the text (helps cross-ref anchoring)
        body = (
            ChunkingHelpers.figure_to_text(block)
            if item.kind == "figure"
            else ChunkingHelpers.table_to_text(block)
        )
        caption_text = "\n".join(c.text or "" for c in captions).strip()
        raw_text = "\n\n".join(p for p in (caption_text, body) if p.strip())

        block_ids = [block.id] + [c.id for c in captions]
        return cls._make_chunk(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=item.kind,
            prov=ChunkingHelpers.aggregate_prov([block, *captions], breadcrumb),
            counter=counter,
            config_hash=config_hash,
        )

    # ─── Chunk factory ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_chunk(
        block_ids: list[str],
        raw_text: str,
        doc_id: str,
        strategy: str,
        prov: dict[str, Any],
        counter: Iterator[int],
        config_hash: str,
        parent_id: str | None = None,
    ) -> Chunk:
        """
        Build a Chunk with a deterministic UUID derived from its content identity + ordinal.

        Args:
            block_ids (list[str]): Source block ids included in the chunk.
            raw_text (str): Raw text content of the chunk.
            doc_id (str): Document identifier.
            strategy (str): Chunking strategy label (splitter name or "figure"/"table").
            prov (dict[str, Any]): Provenance metadata dict.
            counter (Iterator[int]): Ordinal stream for UUID derivation.
            config_hash (str): Chunking configuration hash.
            parent_id (str | None): Parent chunk id for hierarchical mode.

        Returns:
            Chunk: A fully constructed Chunk ready for S5 contextualisation.
        """
        ordinal = next(counter)
        return Chunk(
            id=ChunkingHelpers.stable_chunk_uuid(doc_id, block_ids, config_hash, ordinal),
            document_id=doc_id,
            config_hash=config_hash,
            block_ids=block_ids,
            raw_text=raw_text,
            embed_text="",          # Filled by S5 from prov.heading_path + body
            token_count=ChunkingHelpers.estimate_tokens_text(raw_text),
            strategy=strategy,
            prov=prov,
            parent_id=parent_id,
        )
