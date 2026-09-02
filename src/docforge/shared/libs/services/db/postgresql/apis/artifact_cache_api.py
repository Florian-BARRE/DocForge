# ====== Code Summary ======
# ArtifactCacheApi — the data-access API for the `artifact_cache` pointer table. Lookup is by exact
# ``cache_key`` (the PK); a HIT bumps hit_count + last_hit_at in place (upsert-on-hit); a store is an
# idempotent INSERT (on_conflict_do_nothing, so two concurrent runs computing the same key race
# harmlessly). The rest are the GC read paths: TTL/LRU candidate selection (by coalesce(last_hit_at,
# created_at)), per-collection size accounting, and the ref-count check the orphan S3 sweep needs.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import ArtifactCache


class ArtifactCacheApi:
    """Static data-access API for the artifact-cache pointer table (exact-key lookup + GC reads)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ArtifactCacheApi is a static-only class and cannot be instantiated.")

    # ── Hook read/write path ──────────────────────────────────────────────────────────────────
    @staticmethod
    async def get(session: AsyncSession, cache_key: str) -> ArtifactCache | None:
        """Fetch the cache row for an exact key, or None (a miss)."""
        return await session.get(ArtifactCache, cache_key)

    @staticmethod
    async def record_hit(session: AsyncSession, cache_key: str, now: datetime) -> None:
        """Upsert-on-hit: bump hit_count and stamp last_hit_at for an existing key."""
        await session.execute(
            update(ArtifactCache)
            .where(ArtifactCache.cache_key == cache_key)
            .values(hit_count=ArtifactCache.hit_count + 1, last_hit_at=now)
        )

    @staticmethod
    async def insert(session: AsyncSession, row: ArtifactCache) -> None:
        """Insert a cache pointer row; a concurrent run that already stored the same key is a no-op."""
        statement = (
            pg_insert(ArtifactCache)
            .values(
                cache_key=row.cache_key,
                content_hash=row.content_hash,
                stage_key=row.stage_key,
                artifact_type=row.artifact_type,
                engine_version=row.engine_version,
                document_id=row.document_id,
                collection_id=row.collection_id,
                size_bytes=row.size_bytes,
            )
            .on_conflict_do_nothing(index_elements=["cache_key"])
        )
        await session.execute(statement)

    # ── GC read paths ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    async def list_expired(session: AsyncSession, cutoff: datetime) -> list[ArtifactCache]:
        """Rows whose recency (last_hit_at, else created_at) is strictly before the TTL cutoff."""
        recency = func.coalesce(ArtifactCache.last_hit_at, ArtifactCache.created_at)
        result = await session.execute(select(ArtifactCache).where(recency < cutoff))
        return list(result.scalars().all())

    @staticmethod
    async def collection_sizes(session: AsyncSession) -> list[tuple[uuid.UUID, int]]:
        """Total cached bytes per collection — the input to the per-collection size cap."""
        result = await session.execute(
            select(ArtifactCache.collection_id, func.sum(ArtifactCache.size_bytes)).group_by(
                ArtifactCache.collection_id
            )
        )
        return [(cid, int(total or 0)) for cid, total in result.all()]

    @staticmethod
    async def list_by_recency(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[ArtifactCache]:
        """A collection's rows oldest-first (least-recently-used first) — the LRU eviction order."""
        recency = func.coalesce(ArtifactCache.last_hit_at, ArtifactCache.created_at)
        result = await session.execute(
            select(ArtifactCache)
            .where(ArtifactCache.collection_id == collection_id)
            .order_by(recency.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[ArtifactCache]:
        """Every cache row attributed to a document (dropped when the document is deleted)."""
        result = await session.execute(
            select(ArtifactCache).where(ArtifactCache.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def referenced_hashes(session: AsyncSession, content_hashes: Sequence[str]) -> set[str]:
        """Which of these content hashes ANY surviving cache row still points at (orphan filter)."""
        if not content_hashes:
            return set()
        result = await session.execute(
            select(ArtifactCache.content_hash)
            .where(ArtifactCache.content_hash.in_(list(content_hashes)))
            .distinct()
        )
        return set(result.scalars().all())

    @staticmethod
    async def delete_keys(session: AsyncSession, cache_keys: Sequence[str]) -> None:
        """Remove cache pointer rows by key (the eviction write)."""
        if not cache_keys:
            return
        await session.execute(
            delete(ArtifactCache).where(ArtifactCache.cache_key.in_(list(cache_keys)))
        )

    @staticmethod
    async def delete_for_documents(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """Drop every cache pointer row attributed to any of these deleted documents (rows only —
        the orphaned S3 bytes are reclaimed by the GC's global orphan sweep)."""
        if not document_ids:
            return
        await session.execute(
            delete(ArtifactCache).where(ArtifactCache.document_id.in_(list(document_ids)))
        )


__all__ = ["ArtifactCacheApi"]
