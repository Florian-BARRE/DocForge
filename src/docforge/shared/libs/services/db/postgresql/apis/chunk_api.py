# ====== Code Summary ======
# ChunkApi — the data-access API for the chunk domain: the chunks (enriched text), their composition
# (chunk_block, the IR blocks that form each), and the chunk-level derived rows (generated metadata,
# doc2query questions, entity mentions). `get_by_ids` is the hydration path after a Qdrant search;
# `get_composition_for_document` lets a caller recompute the raw chunks from their blocks.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

from ..tables import Block, Chunk, ChunkBlock, ChunkMetadata, Document, EntityMention


class ChunkApi:
    """Static data-access API for the chunks, their composition and their derived rows."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def persist_chunks(
        session: AsyncSession,
        chunks: Sequence[Chunk],
        composition: Sequence[ChunkBlock],
        *,
        metadata: Sequence[ChunkMetadata] = (),
        entities: Sequence[EntityMention] = (),
    ) -> None:
        """
        Persist a document's chunks and everything hanging off them, in foreign-key order.

        Args:
            session (AsyncSession): The unit of work.
            chunks (Sequence[Chunk]): The chunks (their ids double as Qdrant point ids).
            composition (Sequence[ChunkBlock]): The chunk ↔ block memberships.
            metadata (Sequence[ChunkMetadata]): Per-chunk generated metadata values.
            entities (Sequence[EntityMention]): Extracted entity mentions.
        """
        # 1. Chunks first — the composition and derived rows reference them (and chunk.parent_id
        #    self-references, so all chunks must exist before the links resolve).
        session.add_all(list(chunks))
        await session.flush()
        # 2. Composition + derived rows.
        session.add_all([*composition, *metadata, *entities])

    @staticmethod
    async def get_by_ids(session: AsyncSession, chunk_ids: Sequence[uuid.UUID]) -> list[Chunk]:
        """Fetch chunks by id — the hydration path after a Qdrant search."""
        if not chunk_ids:
            return []
        result = await session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def collections_for_chunks(
        session: AsyncSession, chunk_ids: Sequence[uuid.UUID]
    ) -> list[uuid.UUID]:
        """
        Return the distinct collections owning a set of chunks (via their documents).

        The authorization gate uses this to scope a chunk-mutating request: a scoped key may only
        touch chunks whose documents live in a collection it owns.

        Args:
            session (AsyncSession): The unit of work.
            chunk_ids (Sequence[uuid.UUID]): The chunks the request targets.

        Returns:
            list[uuid.UUID]: The distinct owning collection ids (empty when no chunk matches).
        """
        # 1. Nothing to resolve — an empty target set owns no collection.
        if not chunk_ids:
            return []
        # 2. One joined query maps every chunk to its document's collection, de-duplicated.
        result = await session.execute(
            select(Document.collection_id)
            .join(Chunk, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(chunk_ids))
            .distinct()
        )
        return list(result.scalars())

    @staticmethod
    async def get_for_document(session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
        """Return a document's chunks in order."""
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_indexed_ids_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Return the ids of a document's INDEXED chunks — the Qdrant point ids to patch.

        Only indexed chunks own a point, so this is the exact set a payload denormalisation
        (document-scope filterable metadata → chunk payload) may target. Id-only, no text loaded.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose indexed chunk ids are returned.

        Returns:
            list[uuid.UUID]: The indexed chunk ids (each equals its Qdrant point id).
        """
        result = await session.execute(
            select(Chunk.id).where(Chunk.document_id == document_id, Chunk.is_indexed.is_(True))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_block_locations_for_chunks(
        session: AsyncSession, chunk_ids: Sequence[uuid.UUID]
    ) -> list[tuple[uuid.UUID, str, int, list[float]]]:
        """
        Return (chunk_id, block_id, page, bbox) for a set of chunks — the search-hit location read.

        Joins chunk_block → block so a hit can carry the page + bounding box of the blocks it was
        assembled from (enough for a UI to draw a box on the page image). Ordered by assembly
        ``position`` so the FIRST row per chunk is its primary (leading) block. The bbox is the
        block's stored, normalised [x0, y0, x1, y1] in [0, 1].

        Args:
            session (AsyncSession): The unit of work.
            chunk_ids (Sequence[uuid.UUID]): The chunks to locate.

        Returns:
            list[tuple[uuid.UUID, str, int, list[float]]]: One row per (chunk, block), ordered by
            (chunk_id, position). Empty when nothing matches.
        """
        if not chunk_ids:
            return []
        result = await session.execute(
            select(ChunkBlock.chunk_id, ChunkBlock.block_id, Block.page, Block.bbox)
            .join(Block, Block.id == ChunkBlock.block_id)
            .where(ChunkBlock.chunk_id.in_(chunk_ids))
            .order_by(ChunkBlock.chunk_id, ChunkBlock.position)
        )
        return [(row[0], row[1], row[2], list(row[3])) for row in result.all()]

    @staticmethod
    async def get_composition_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[ChunkBlock]:
        """
        Return every chunk↔block membership of a document's chunks in ONE query.

        Ordered by (chunk_id, position) so a caller can group by chunk and keep the assembly
        order, avoiding a per-chunk N+1 when exploring a whole document's chunks.
        """
        result = await session.execute(
            select(ChunkBlock)
            .join(Chunk, ChunkBlock.chunk_id == Chunk.id)
            .where(Chunk.document_id == document_id)
            .order_by(ChunkBlock.chunk_id, ChunkBlock.position)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_metadata_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[ChunkMetadata]:
        """
        Return every generated metadata value of a document's chunks in ONE query.

        Avoids a per-chunk N+1 when exploring a whole document's chunks — the caller groups
        the rows by chunk_id.
        """
        result = await session.execute(
            select(ChunkMetadata)
            .join(Chunk, ChunkMetadata.chunk_id == Chunk.id)
            .where(Chunk.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def upsert_metadata(session: AsyncSession, values: Sequence[ChunkMetadata]) -> None:
        """
        Insert-or-update generated metadata values on (chunk_id, field_id).

        The post-hoc metagen path: an LLM computes a field over EXISTING chunks and the values
        land here without re-chunking — a second run for the same field overwrites in place.
        """
        if not values:
            return
        # The raw-insert path bypasses the ORM column default, so apply it here: a transient
        # ChunkMetadata built without `origin` carries None, which would violate NOT NULL.
        rows = [
            {
                "chunk_id": v.chunk_id,
                "field_id": v.field_id,
                "value": v.value,
                "origin": v.origin or FieldOrigin.GENERATED,
            }
            for v in values
        ]
        statement = pg_insert(ChunkMetadata).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["chunk_id", "field_id"],
            set_={"value": statement.excluded.value, "origin": statement.excluded.origin},
        )
        await session.execute(statement)

    @staticmethod
    async def mark_indexed(session: AsyncSession, chunk_ids: Sequence[uuid.UUID]) -> None:
        """Flag chunks as indexed — called right after their Qdrant upsert succeeds."""
        if not chunk_ids:
            return
        await session.execute(update(Chunk).where(Chunk.id.in_(chunk_ids)).values(is_indexed=True))

    @staticmethod
    async def delete_for_document(session: AsyncSession, document_id: uuid.UUID) -> None:
        """Delete a document's chunks (cascades composition + derived rows) — the re-ingest purge."""
        await session.execute(delete(Chunk).where(Chunk.document_id == document_id))


__all__ = ["ChunkApi"]
