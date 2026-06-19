# ====== Code Summary ======
# HierAssemblerHelpers — static helper for hierarchical chunk assembly.
# Extracted from ChunkAssembler to isolate the hierarchical processing path
# (_section_with_parent, _flat_section_chunk).

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# ====== Internal Project Imports ======
from libs.domain.ir.chunk import Chunk

from ..chunking import ChunkingHelpers, SectionSplitter

# ====== Local Project Imports ======
from .models import _PARENT_STRATEGY, _Segment


class HierAssemblerHelpers:
    """
    Static helper implementing the hierarchical assembly path of ChunkAssembler.

    Covers: per-section parent+children emission, flat fallback for undivided sections.
    Methods are called from ChunkAssembler via delegation — never instantiated directly.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — all methods are static or classmethods."""
        raise TypeError("HierAssemblerHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    async def section_with_parent(
        cls,
        seg: _Segment,
        doc_id: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
        make_chunk_fn: Any,
    ) -> list[Chunk]:
        """
        Emit a flat chunk when a section fits/cannot divide, else a parent + its children.

        Args:
            seg (_Segment): The section to process.
            doc_id (str): Document identifier.
            counter (Iterator[int]): Ordinal stream.
            splitter (SectionSplitter): Split method.
            config_hash (str): Configuration hash.
            make_chunk_fn (callable): Shared chunk factory from ChunkAssembler._make_chunk.

        Returns:
            list[Chunk]: One flat chunk or [parent, child1, child2, ...].
        """
        breadcrumb = " > ".join(seg.path)
        seg_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in seg.blocks)

        # 1. Fits in the budget → one flat chunk (is its own context)
        if seg_tokens <= splitter.max_tokens:
            return [cls.flat_section_chunk(seg, doc_id, breadcrumb, counter, splitter, config_hash, make_chunk_fn)]

        # 2. Oversize → split; a single piece means the splitter could not divide it
        pieces = await splitter.split_section(seg.blocks)
        if len(pieces) <= 1:
            return [cls.flat_section_chunk(seg, doc_id, breadcrumb, counter, splitter, config_hash, make_chunk_fn)]

        # 3. Parent (full section) over its children (the pieces)
        parent = make_chunk_fn(
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
            chunks.append(make_chunk_fn(
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
    def flat_section_chunk(
        cls,
        seg: _Segment,
        doc_id: str,
        breadcrumb: str,
        counter: Iterator[int],
        splitter: SectionSplitter,
        config_hash: str,
        make_chunk_fn: Any,
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
            make_chunk_fn (callable): Shared chunk factory from ChunkAssembler._make_chunk.

        Returns:
            Chunk: A single flat chunk for the section.
        """
        return make_chunk_fn(
            block_ids=[b.id for b in seg.blocks],
            raw_text=ChunkingHelpers.blocks_to_text(seg.blocks),
            doc_id=doc_id,
            strategy=splitter.name,
            prov=ChunkingHelpers.aggregate_prov(seg.blocks, breadcrumb),
            counter=counter,
            config_hash=config_hash,
        )
