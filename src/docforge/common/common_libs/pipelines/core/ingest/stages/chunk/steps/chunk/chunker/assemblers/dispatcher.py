# ====== Code Summary ======
# ChunkAssembler — thin dispatcher that converts traversal items (_Segment / _Special) into Chunk
# objects.  Delegates flat packing to FlatPackerHelpers, hierarchical assembly to
# HierAssemblerHelpers, and the shared chunk factory + special-block emitter to ChunkFactoryHelpers.

# ====== Standard Library Imports ======
from collections.abc import Iterator

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import Block

# ====== Local Project Imports ======
from ..chunk_factory import ChunkFactoryHelpers
from ..models import _Segment, _Special
from ..strategies.base import SectionSplitter
from .flat import FlatPackerHelpers
from .hierarchical import HierAssemblerHelpers


class ChunkAssembler:
    """
    Static dispatcher that assembles Chunk objects from structured traversal items.

    Delegates flat packing (greedy merge + oversize split) to FlatPackerHelpers and
    hierarchical parent/child emission to HierAssemblerHelpers.  The shared chunk factory
    (make_chunk) and special-block emitter (emit_special) live in ChunkFactoryHelpers.
    """

    logger = loggerplusplus.bind(identifier="ChunkAssembler")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — all methods are static or classmethods."""
        raise TypeError("ChunkAssembler is a static-only class and cannot be instantiated.")

    # --- Flat processing (delegates to FlatPackerHelpers) ---------------------

    @classmethod
    async def process_flat(
        cls,
        items: list["_Segment | _Special"],
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
        make_chunk = ChunkFactoryHelpers.make_chunk
        chunks: list[Chunk] = []
        pending: list[_Segment] = []
        for item in items:
            if isinstance(item, _Segment):
                pending.append(item)
                continue
            # A special interrupts the text flow -> flush pending sections first
            chunks.extend(
                await FlatPackerHelpers.pack_segments(
                    pending, doc_id, counter, splitter, merge_short, config_hash, make_chunk
                )
            )
            pending = []
            chunks.append(
                ChunkFactoryHelpers.emit_special(item, doc_id, caption_of, counter, config_hash)
            )
        chunks.extend(
            await FlatPackerHelpers.pack_segments(
                pending, doc_id, counter, splitter, merge_short, config_hash, make_chunk
            )
        )
        cls.logger.debug(f"ChunkAssembler flat: assembled {len(chunks)} chunks for doc_id={doc_id!r}")
        return chunks

    # --- Hierarchical processing (delegates to HierAssemblerHelpers) ----------

    @classmethod
    async def process_hierarchical(
        cls,
        items: list["_Segment | _Special"],
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
        make_chunk = ChunkFactoryHelpers.make_chunk
        chunks: list[Chunk] = []
        for item in items:
            if isinstance(item, _Special):
                chunks.append(
                    ChunkFactoryHelpers.emit_special(item, doc_id, caption_of, counter, config_hash)
                )
                continue
            chunks.extend(
                await HierAssemblerHelpers.section_with_parent(
                    item, doc_id, counter, splitter, config_hash, make_chunk
                )
            )
        return chunks


__all__ = ["ChunkAssembler"]
