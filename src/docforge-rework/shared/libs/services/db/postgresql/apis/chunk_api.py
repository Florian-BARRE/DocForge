# ====== Code Summary ======
# ChunkApi — the data-access API for the chunk domain: the chunks (enriched text), their composition
# (chunk_block, the IR blocks that form each), and the chunk-level derived rows (generated metadata,
# doc2query questions, entity mentions). `get_by_ids` is the hydration path after a Qdrant search;
# `get_composition` lets a caller recompute the raw chunk from its blocks.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

from ..tables import Chunk, ChunkBlock, ChunkMetadata, ChunkQuery, EntityMention


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
        queries: Sequence[ChunkQuery] = (),
        entities: Sequence[EntityMention] = (),
    ) -> None:
        """
        Persist a document's chunks and everything hanging off them, in foreign-key order.

        Args:
            session (AsyncSession): The unit of work.
            chunks (Sequence[Chunk]): The chunks (their ids double as Qdrant point ids).
            composition (Sequence[ChunkBlock]): The chunk ↔ block memberships.
            metadata (Sequence[ChunkMetadata]): Per-chunk generated metadata values.
            queries (Sequence[ChunkQuery]): doc2query synthetic questions.
            entities (Sequence[EntityMention]): Extracted entity mentions.
        """
        # 1. Chunks first — the composition and derived rows reference them (and chunk.parent_id
        #    self-references, so all chunks must exist before the links resolve).
        session.add_all(list(chunks))
        await session.flush()
        # 2. Composition + derived rows.
        session.add_all([*composition, *metadata, *queries, *entities])

    @staticmethod
    async def get_by_ids(
        session: AsyncSession, chunk_ids: Sequence[uuid.UUID]
    ) -> list[Chunk]:
        """Fetch chunks by id — the hydration path after a Qdrant search."""
        if not chunk_ids:
            return []
        result = await session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def get_for_document(session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
        """Return a document's chunks in order."""
        result = await session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_composition(session: AsyncSession, chunk_id: uuid.UUID) -> list[ChunkBlock]:
        """Return a chunk's block memberships, in assembly order (to recompute the raw chunk)."""
        result = await session.execute(
            select(ChunkBlock)
            .where(ChunkBlock.chunk_id == chunk_id)
            .order_by(ChunkBlock.position)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_composition_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[ChunkBlock]:
        """
        Return every chunk↔block membership of a document's chunks in ONE query.

        Ordered by (chunk_id, position) so a caller can group by chunk and keep the assembly
        order — the bulk form of `get_composition`, avoiding a per-chunk N+1 when exploring a
        whole document's chunks.
        """
        result = await session.execute(
            select(ChunkBlock)
            .join(Chunk, ChunkBlock.chunk_id == Chunk.id)
            .where(Chunk.document_id == document_id)
            .order_by(ChunkBlock.chunk_id, ChunkBlock.position)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_metadata(session: AsyncSession, chunk_id: uuid.UUID) -> list[ChunkMetadata]:
        """Return a chunk's generated metadata values (inspection + indexing)."""
        result = await session.execute(
            select(ChunkMetadata).where(ChunkMetadata.chunk_id == chunk_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_metadata_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[ChunkMetadata]:
        """
        Return every generated metadata value of a document's chunks in ONE query.

        The bulk form of `get_metadata`, avoiding a per-chunk N+1 when exploring a whole
        document's chunks — the caller groups the rows by chunk_id.
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
        await session.execute(
            update(Chunk).where(Chunk.id.in_(chunk_ids)).values(is_indexed=True)
        )

    @staticmethod
    async def delete_for_document(session: AsyncSession, document_id: uuid.UUID) -> None:
        """Delete a document's chunks (cascades composition + derived rows) — the re-ingest purge."""
        await session.execute(delete(Chunk).where(Chunk.document_id == document_id))


__all__ = ["ChunkApi"]
