# ====== Code Summary ======
# CollectionDeleter — the coherent cross-store deletion of a collection: refuse while aliased or while
# a rebuild RUNS, cancel in-flight jobs first (own commit, so a live worker observes the flag), drop
# the derived index (Qdrant), cascade the truth (PG), purge the blobs nothing references anymore (the
# multi-reference safety filter), S3 last — after the PG commit — then reclaim trace payloads.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import (
    BlobApi,
    CollectionAliasApi,
    CollectionApi,
    JobApi,
    RebuildJobApi,
)
from shared_libs.services.db.postgresql.tables import JobStatus
from shared_libs.services.db.qdrant import QdrantClient, QdrantCollectionApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .collection_alias_payloads import CollectionAliasedError
from .helpers import DatabaseHelpers
from .index_rebuild_payloads import IndexRebuildActiveError
from .trace_purge import TracePurgeHelper


class CollectionDeleter(LoggerClass):
    """Cross-store collection deletion — jobs cancelled, Qdrant, PG cascade, guarded blob purge."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient, s3: S3Client) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (jobs, cascade, blob registry).
            qdrant (QdrantClient): The derived vector index dropped first.
            s3 (S3Client): The object store purged last (orphan blobs + trace payloads).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._s3 = s3

    async def _cancel_active_jobs(self, collection_id: uuid.UUID) -> int:
        """
        Force every in-flight job of a collection to CANCELLED — run BEFORE the cascade delete.

        A delete cascade removes the ``job`` rows (and the collection's documents) while a worker may
        still be mid-run, inserting ``job_stage_event`` rows and, at its persist phase, document/chunk
        rows — all FK-referencing the about-to-vanish rows, which raises an IntegrityError in the
        worker. Cancelling first closes that race at the source: the CONDITIONAL ``mark_terminal``
        transition flips each live job to CANCELLED and raises ``cancel_requested``, so a live worker
        aborts its run gracefully at its next stage boundary — before it writes anything the cascade
        will delete (no wasted compute, no crash). Committed in its OWN transaction so the worker can
        actually OBSERVE the flag; the cascade follows. Idempotent: a job that already went terminal
        no longer matches the live-status guard (a clean no-op).

        Args:
            collection_id (uuid.UUID): The collection whose in-flight jobs are stopped.

        Returns:
            int: The number of live jobs transitioned to CANCELLED.
        """
        # 1. List + conditionally terminate the live jobs in one committed transaction.
        cancelled = 0
        now = datetime.now(UTC)
        async with self._postgres.session() as session:
            for job in await JobApi.list_active_for_collection(session, collection_id):
                terminated = await JobApi.mark_terminal(
                    session,
                    job.id,
                    status=JobStatus.CANCELLED,
                    reason="collection deleted — ingestion cancelled",
                    finished_at=now,
                )
                if terminated is not None:
                    cancelled += 1
        # 2. Report how many runs were stopped (the worker aborts each at its next stage boundary).
        if cancelled:
            self.logger.info(
                f"Cancelled {cancelled} in-flight job(s) before deleting collection {collection_id}"
            )
        return cancelled

    async def delete(self, collection_id: uuid.UUID) -> bool:
        """
        Delete a collection everywhere — in-flight jobs cancelled, Qdrant, PG cascade, blob purge.

        Raises:
            IndexRebuildActiveError: A rebuild_index job is RUNNING on the collection.
            CollectionAliasedError: Collection aliases still target it (checked BEFORE any destructive
                step; the RESTRICT FK on collection_alias is only the backstop).

        Returns:
            bool: Whether the collection existed.
        """
        # -1. A RUNNING rebuild owns the store mid-copy/swap: refuse rather than force-cancel it under
        #     its feet (a queued one is safely cancelled below — the worker skips it at dequeue). An
        #     aliased collection is refused too: deleting it would break every key/app bound to the alias.
        async with self._postgres.session() as session:
            aliases = await CollectionAliasApi.names_for(session, collection_id)
            rebuild = await RebuildJobApi.active_rebuild(session, collection_id)
        if aliases:
            raise CollectionAliasedError(collection_id, aliases)
        if rebuild is not None and rebuild.status == JobStatus.RUNNING:
            raise IndexRebuildActiveError(collection_id, rebuild.id)
        # 0. Stop in-flight work FIRST so a live worker aborts before the cascade deletes the rows its
        #    mid-run inserts reference (else an FK IntegrityError in the worker). Committed on its own
        #    so the worker observes the cancel flag; a vanished job at its next boundary is a stop too.
        await self._cancel_active_jobs(collection_id)
        # 1. Drop the derived index first — an orphan Qdrant point would break search hydration.
        await QdrantCollectionApi.drop(
            self._qdrant.raw, DatabaseHelpers.qdrant_collection_name(collection_id)
        )
        # 2. One PG transaction: gather purge candidates, cascade-delete, keep only true orphans.
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return False
            # Capture the collection's job ids BEFORE the cascade removes them — their trace payloads
            # are reclaimed from the object store after the commit (the DB rows cascade; only S3 needs it).
            trace_job_ids = await JobApi.list_job_ids_for_collection(session, collection_id)
            candidates = await BlobApi.collect_hashes_for_collection(session, collection_id)
            await CollectionApi.delete(session, collection_id)
            await session.flush()
            # Guarded purge: the reference re-check lives in the DELETE, so a hash a concurrent ingest
            # re-referenced between the flush and the commit is kept; RETURNING gives the S3 delete set.
            orphans = await BlobApi.delete_unreferenced(session, candidates)
        # 3. S3 last, AFTER the commit — a failed S3 delete only leaves harmless orphan objects.
        if orphans:
            async with self._s3.client() as s3:
                await S3ObjectApi.delete_many(s3, self._s3.bucket, orphans)
        # 4. Reclaim the collection's runs' full-trace payloads (best-effort — never fails the delete).
        await TracePurgeHelper.purge(self._postgres, self._s3, trace_job_ids)
        self.logger.info(f"Collection {collection_id} deleted ({len(orphans)} blobs purged)")
        return True


__all__ = ["CollectionDeleter"]
