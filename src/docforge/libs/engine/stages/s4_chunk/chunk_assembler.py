# ====== Code Summary ======
# ChunkAssembler — thin dispatcher that converts traversal items (_Segment / _Special) into Chunk
# objects.  Delegates flat packing to FlatPackerHelpers (chunk_assembler_flat.py) and
# hierarchical assembly to HierAssemblerHelpers (chunk_assembler_hier.py).
# Owns the shared _emit_special and _make_chunk methods used by both paths.

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
from .chunk_assembler_flat import FlatPackerHelpers
from .chunk_assembler_hier import HierAssemblerHelpers
from .models import _Segment, _Special


class ChunkAssembler:
    """
    Static dispatcher that assembles Chunk objects from structured traversal items.

    Delegates flat packing (greedy merge + oversize split) to FlatPackerHelpers and
    hierarchical parent/child emission to HierAssemblerHelpers.  Owns the shared
    special-block emitter (_emit_special) and chunk factory (_make_chunk) used by both.
    """

    logger = loggerplusplus.bind(identifier="ChunkAssembler")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — all methods are static or classmethods."""
        raise TypeError("ChunkAssembler is a static-only class and cannot be instantiated.")

    # ─── Flat processing (delegates to FlatPackerHelpers) ─────────────────────

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
                await FlatPackerHelpers.pack_segments(
                    pending, doc_id, counter, splitter, merge_short, config_hash, cls._make_chunk
                )
            )
            pending = []
            chunks.append(cls._emit_special(item, doc_id, caption_of, counter, config_hash))
        chunks.extend(
            await FlatPackerHelpers.pack_segments(
                pending, doc_id, counter, splitter, merge_short, config_hash, cls._make_chunk
            )
        )
        cls.logger.debug(f"ChunkAssembler flat: assembled {len(chunks)} chunks for doc_id={doc_id!r}")
        return chunks

    # ─── Hierarchical processing (delegates to HierAssemblerHelpers) ──────────

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
                await HierAssemblerHelpers.section_with_parent(
                    item, doc_id, counter, splitter, config_hash, cls._make_chunk
                )
            )
        return chunks

    # ─── Special-block chunk emitter (shared by both paths) ───────────────────

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

    # ─── Chunk factory (shared by both paths) ──────────────────────────────────

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
