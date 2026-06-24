# ====== Code Summary ======
# FlatPackerHelpers — static helper for flat chunk packing and oversize section splitting.
# Extracted from ChunkAssembler to isolate the flat processing path
# (_pack_segments, _segments_to_chunk, _split_section_to_chunks).
# All three methods are tightly coupled: _pack_segments calls both _segments_to_chunk
# and _split_section_to_chunks, so they belong in the same file.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import Block

from ..helpers.text import ChunkingHelpers
from ..strategies.base import SectionSplitter

# ====== Local Project Imports ======
from ..models import _Segment


class FlatPackerHelpers:
    """
    Static helper implementing the flat-packing path of ChunkAssembler.

    Covers: greedy sibling-segment packing, oversize section splitting,
    and segment-to-chunk merging.  Methods are called from ChunkAssembler
    via delegation — never instantiated directly.
    """

    logger = loggerplusplus.bind(identifier="FlatPackerHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — all methods are static or classmethods."""
        raise TypeError("FlatPackerHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def pack_segments(
        cls,
        segments: list[_Segment],
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        merge_short: bool,
        config_hash: str,
        make_chunk_fn: Any,
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
            make_chunk_fn (callable): Shared chunk factory from ChunkAssembler._make_chunk.

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
                    chunks.append(cls.segments_to_chunk(buffer, doc_id, counter, splitter, config_hash, make_chunk_fn))
                    buffer, buf_tokens = [], 0
                chunks.extend(
                    await cls.split_section_to_chunks(seg, doc_id, counter, splitter, config_hash, make_chunk_fn)
                )
                continue

            # 2. Packing this segment would overflow (or merging is off) → flush first
            if buffer and (not merge_short or buf_tokens + seg_tokens > max_tokens):
                chunks.append(cls.segments_to_chunk(buffer, doc_id, counter, splitter, config_hash, make_chunk_fn))
                buffer, buf_tokens = [], 0

            buffer.append(seg)
            buf_tokens += seg_tokens

        if buffer:
            chunks.append(cls.segments_to_chunk(buffer, doc_id, counter, splitter, config_hash, make_chunk_fn))
        return chunks

    @classmethod
    def segments_to_chunk(
        cls,
        segments: list[_Segment],
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
        make_chunk_fn: Any,
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
            make_chunk_fn (callable): Shared chunk factory from ChunkAssembler._make_chunk.

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
        return make_chunk_fn(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=splitter.name,
            prov=ChunkingHelpers.aggregate_prov(all_blocks, " > ".join(common)),
            counter=counter,
            config_hash=config_hash,
        )

    @classmethod
    async def split_section_to_chunks(
        cls,
        seg: _Segment,
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
        make_chunk_fn: Any,
    ) -> list[Chunk]:
        """
        Split one oversize section via the configured method, all sharing its breadcrumb.

        Args:
            seg (_Segment): Section whose token count exceeds max_tokens.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): The split method to invoke.
            config_hash (str): Configuration hash.
            make_chunk_fn (callable): Shared chunk factory from ChunkAssembler._make_chunk.

        Returns:
            list[Chunk]: Sub-chunks produced by the splitter.
        """
        pieces = await splitter.split_section(seg.blocks)
        breadcrumb = " > ".join(seg.path)
        bmap = {b.id: b for b in seg.blocks}
        chunks: list[Chunk] = []
        for piece in pieces:
            blocks = [bmap[bid] for bid in piece.block_ids if bid in bmap]
            chunks.append(make_chunk_fn(
                block_ids=piece.block_ids,
                raw_text=piece.text,
                doc_id=doc_id,
                strategy=splitter.name,
                prov=ChunkingHelpers.aggregate_prov(blocks, breadcrumb),
                counter=counter,
                config_hash=config_hash,
            ))
        return chunks
