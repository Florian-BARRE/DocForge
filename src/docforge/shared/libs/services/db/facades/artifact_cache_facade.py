# ====== Code Summary ======
# ArtifactCacheFacade — the data-layer gateway for the per-collection stage-artifact cache. It backs
# the worker's StageCacheHook (exact-key lookup, byte load from S3, upsert-on-hit, and the store =
# S3 put + blob register + pointer insert) AND the GC cron (TTL + per-collection LRU size cap, plus
# the ref-count orphan sweep that deletes an S3 stage-artifact blob once the LAST cache_key pointing
# at it is gone). Cross-store order mirrors IngestionFacade: bytes first, pointer rows after; on
# eviction, pointer rows first, S3 objects only once proven unreferenced.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import delete, select

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ArtifactCacheApi, BlobApi
from shared_libs.services.db.postgresql.tables import ArtifactCache, Blob, BlobKind
from shared_libs.services.db.s3 import S3Client, S3Object, S3ObjectApi

# The stored stage-artifact bytes are an opaque msgpack frame (see ArtifactCodec).
_STAGE_ARTIFACT_MIME = "application/x-msgpack"


@dataclass(slots=True)
class ArtifactCacheGcSummary:
    """What one GC sweep reclaimed — evicted pointer rows and the S3 stage-artifact blobs freed.

    Attributes:
        evicted_rows (int): artifact_cache pointer rows deleted (TTL + size-cap eviction).
        freed_blobs (int): S3 stage-artifact objects (and their blob rows) deleted as now-orphaned.
    """

    evicted_rows: int
    freed_blobs: int


class ArtifactCacheFacade(LoggerClass):
    """Store gateway for the stage-artifact cache — the hook's I/O and the GC sweep."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular store (pointer table + blob registry).
            s3 (S3Client): The blob store holding the cached bytes.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    # ── Hook read/write path ──────────────────────────────────────────────────────────────────
    async def lookup(self, cache_key: str) -> ArtifactCache | None:
        """Return the pointer row for an exact cache key, or None (a miss)."""
        async with self._postgres.session() as session:
            return await ArtifactCacheApi.get(session, cache_key)

    async def load_bytes(self, content_hash: str) -> bytes:
        """Read a cached artefact's raw bytes from the blob store by its content hash."""
        async with self._s3.client() as client:
            return await S3ObjectApi.get(client, self._s3.bucket, content_hash)

    async def record_hit(self, cache_key: str) -> None:
        """Upsert-on-hit: bump hit_count and stamp last_hit_at for the served key."""
        async with self._postgres.session() as session:
            await ArtifactCacheApi.record_hit(session, cache_key, datetime.now(UTC))

    async def store(self, row: ArtifactCache, data: bytes) -> None:
        """
        Persist a freshly-produced stage artefact: S3 bytes first, then the registry + pointer rows.

        Bytes-first mirrors IngestionFacade.store_blobs — a registry write that then failed leaves a
        harmless orphan object, whereas the reverse would register a row whose bytes do not exist. The
        blob row (idempotent per content hash) and the pointer INSERT (on_conflict_do_nothing) both
        tolerate a concurrent run that already stored the same content.

        Args:
            row (ArtifactCache): The pointer row to insert (key/hash/attribution/size already set).
            data (bytes): The serialised artefact bytes (their sha256 == row.content_hash).
        """
        # 1. The bytes (key = content hash, so identical artefacts dedup in S3 and the registry).
        async with self._s3.client() as client:
            await S3ObjectApi.put_many(
                client,
                self._s3.bucket,
                [S3Object(key=row.content_hash, data=data, content_type=_STAGE_ARTIFACT_MIME)],
            )
        # 2. Register the blob (STAGE_ARTIFACT) and the cache pointer — one session.
        async with self._postgres.session() as session:
            await BlobApi.register(
                session,
                Blob(
                    content_hash=row.content_hash,
                    s3_key=row.content_hash,
                    mime_type=_STAGE_ARTIFACT_MIME,
                    size_bytes=row.size_bytes,
                    kind=BlobKind.STAGE_ARTIFACT,
                ),
            )
            await ArtifactCacheApi.insert(session, row)

    # ── GC ────────────────────────────────────────────────────────────────────────────────────
    async def prune(
        self, now: datetime, ttl: timedelta, max_bytes_per_collection: int
    ) -> ArtifactCacheGcSummary:
        """
        Evict stale/over-cap cache rows (TTL + per-collection LRU size cap) and sweep freed S3 blobs.

        Args:
            now (datetime): The sweep's reference time.
            ttl (timedelta): Rows untouched for longer than this (by last_hit_at, else created_at)
                are evicted. A non-positive TTL disables the TTL pass (size cap still applies).
            max_bytes_per_collection (int): Per-collection byte ceiling; the least-recently-used rows
                over it are evicted. A non-positive cap disables the size pass.

        Returns:
            ArtifactCacheGcSummary: Evicted pointer count + freed S3 blob count.
        """
        # 1. Select + delete eviction victims (TTL + per-collection LRU) — one write session.
        async with self._postgres.session() as session:
            evict_keys, _freed = await self.__select_victims(
                session, now, ttl, max_bytes_per_collection
            )
            if evict_keys:
                await ArtifactCacheApi.delete_keys(session, list(evict_keys))

        # 2. Global orphan sweep: reclaim EVERY stage-artifact blob no pointer row references anymore
        #    — whatever freed it (this eviction, a prior crash, a document delete). Ref-count safe.
        freed_blobs = await self.__sweep_orphan_blobs()
        if evict_keys or freed_blobs:
            self.logger.info(
                f"Artifact-cache GC evicted {len(evict_keys)} row(s), freed {freed_blobs} blob(s)"
            )
        return ArtifactCacheGcSummary(evicted_rows=len(evict_keys), freed_blobs=freed_blobs)

    async def drop_for_document(self, document_id: uuid.UUID) -> int:
        """
        Drop every cache row attributed to a deleted document, then sweep any blob it orphaned.

        Args:
            document_id (uuid.UUID): The document being deleted.

        Returns:
            int: The number of cache pointer rows removed.
        """
        async with self._postgres.session() as session:
            rows = await ArtifactCacheApi.list_for_document(session, document_id)
            if not rows:
                return 0
            await ArtifactCacheApi.delete_keys(session, [row.cache_key for row in rows])
            removed = len(rows)
        await self.__sweep_orphan_blobs()
        return removed

    async def __select_victims(
        self, session, now: datetime, ttl: timedelta, max_bytes_per_collection: int
    ) -> tuple[set[str], set[str]]:
        """Collect the cache keys to evict (TTL then per-collection LRU cap). The second tuple slot
        is unused (orphan reclamation is a global sweep) — kept for a readable call site."""
        evict_keys: set[str] = set()
        # 1. TTL: anything not touched within the window.
        if ttl > timedelta(0):
            for row in await ArtifactCacheApi.list_expired(session, now - ttl):
                evict_keys.add(row.cache_key)
        # 2. Per-collection LRU size cap: keep the most-recent rows up to the cap, evict the rest.
        if max_bytes_per_collection > 0:
            for collection_id, total in await ArtifactCacheApi.collection_sizes(session):
                if total <= max_bytes_per_collection:
                    continue
                rows = await ArtifactCacheApi.list_by_recency(session, collection_id)
                kept = 0
                # Walk newest-first: fill the budget with the freshest rows, evict everything older.
                for row in reversed(rows):
                    if row.cache_key in evict_keys:
                        continue
                    if kept + row.size_bytes <= max_bytes_per_collection:
                        kept += row.size_bytes
                    else:
                        evict_keys.add(row.cache_key)
        return evict_keys, set()

    async def __sweep_orphan_blobs(self) -> int:
        """Delete every STAGE_ARTIFACT blob no cache pointer references anymore (S3 + registry row).

        A stage-artifact blob is referenced ONLY by artifact_cache rows (never by a document/page/
        figure column), so "no cache row points at this content_hash" is the complete orphan test —
        it safely reclaims blobs freed by eviction, a document delete, or a crashed store.
        """
        # 1. Find orphans: stage-artifact blobs whose content_hash is absent from artifact_cache.
        referenced = select(ArtifactCache.content_hash)
        async with self._postgres.session() as session:
            result = await session.execute(
                select(Blob.content_hash).where(
                    Blob.kind == BlobKind.STAGE_ARTIFACT,
                    Blob.content_hash.notin_(referenced),
                )
            )
            hashes = list(result.scalars().all())
        if not hashes:
            return 0
        # 2. S3 objects first, then the registry rows (a leftover row with no bytes would be worse).
        async with self._s3.client() as client:
            await S3ObjectApi.delete_many(client, self._s3.bucket, hashes)
        async with self._postgres.session() as session:
            await session.execute(
                delete(Blob).where(
                    Blob.content_hash.in_(hashes), Blob.kind == BlobKind.STAGE_ARTIFACT
                )
            )
        return len(hashes)


__all__ = ["ArtifactCacheFacade", "ArtifactCacheGcSummary"]
