# ====== Code Summary ======
# ChunkFactoryHelpers — the shared Chunk factory and atomic special-block emitter used by
# both the flat and hierarchical assembly paths.  make_chunk derives a deterministic UUID
# from each chunk's content identity + ordinal; emit_special co-locates an atomic
# FIGURE/TABLE with its caption.  Extracted from ChunkAssembler so the dispatcher stays thin.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# ====== Internal Project Imports ======
from libs.domain.ir.chunk import Chunk
from libs.domain.ir.models import Block

from ..chunking import ChunkingHelpers

# ====== Local Project Imports ======
from .models import _Special


class ChunkFactoryHelpers:
    """
    Static factory helpers shared by the flat and hierarchical assembly paths.

    Owns the deterministic Chunk constructor (``make_chunk``) and the atomic special-block
    emitter (``emit_special``).  All methods are static — there is no instance state.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ChunkFactoryHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def make_chunk(
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

    @classmethod
    def emit_special(
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
        return cls.make_chunk(
            block_ids=block_ids,
            raw_text=raw_text,
            doc_id=doc_id,
            strategy=item.kind,
            prov=ChunkingHelpers.aggregate_prov([block, *captions], breadcrumb),
            counter=counter,
            config_hash=config_hash,
        )


# ------------------- Public API ------------------- #
__all__ = ["ChunkFactoryHelpers"]
