# ====== Code Summary ======
# IndexRebuildGuards — the API-side 409 contract around the rebuild_index job: map a live rebuild to
# ``rebuild_index_active`` (upload, single + bulk reingest, a 2nd rebuild), a busy collection to
# ``collection_busy`` (a rebuild over live jobs), and refuse a bulk reingest with
# ``rebuild_index_required`` while the store lacks a named vector the schema needs. That last one is a
# DELIBERATE deviation from "auto-route the reingest to a rebuild": a reingest can never add a named
# vector to a live Qdrant collection, so the caller is told to run rebuild_index explicitly. Upload and
# single reingest get a NARROWER ``rebuild_index_required`` pre-check: only the chunk-scope
# semantic/lexical vectors every chunk point carries (the worker's persistence guard would otherwise
# reject them only AFTER the paid parse/metagen/embed run). Two more refusals protect a running rebuild:
# a legacy chunk-scope lexical schema is ``rebuild_unsupported_chunk_lexical`` (the copy would destroy
# those vectors for good), and a FORCED cancel of a RUNNING rebuild on a LIVE worker is
# ``rebuild_force_cancel_refused`` (it would lift the ingest lock while the copy continues; the
# cooperative cancel aborts it pre-swap instead). On a dead worker nothing copies, so force is allowed.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope
from shared_libs.services.db import Database
from shared_libs.services.db.facades import (
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildUnsupportedError,
)
from shared_libs.services.db.postgresql.tables import Job, JobKind, JobStatus

# The route a caller is pointed to (kept in sync with the search 422 hint).
REBUILD_ROUTE = "POST /api/v1/collections/{collection_id}/rebuild-index"


class IndexRebuildGuards:
    """Static 409 builders + pre-checks for the rebuild_index admission contract."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IndexRebuildGuards is a static-only class and cannot be instantiated.")

    @staticmethod
    def active_conflict(error: IndexRebuildActiveError) -> HTTPException:
        """409 ``rebuild_index_active`` naming the live rebuild job."""
        return HTTPException(
            status_code=409,
            detail={
                "code": "rebuild_index_active",
                "detail": f"Collection {error.collection_id} is rebuilding its index; retry once "
                f"job {error.job_id} has finished.",
                "job_id": str(error.job_id) if error.job_id else None,
            },
        )

    @staticmethod
    def busy_conflict(error: CollectionBusyError) -> HTTPException:
        """409 ``collection_busy`` naming the live jobs blocking a rebuild."""
        return HTTPException(
            status_code=409,
            detail={
                "code": "collection_busy",
                "detail": f"Collection {error.collection_id} has {len(error.job_ids)} active "
                f"job(s); rebuild its index once they have finished.",
                "job_ids": [str(job_id) for job_id in error.job_ids],
            },
        )

    @staticmethod
    def unsupported_conflict(error: RebuildUnsupportedError) -> HTTPException:
        """409 ``rebuild_unsupported_chunk_lexical`` naming the legacy chunk-scope lexical fields."""
        return HTTPException(
            status_code=409,
            detail={
                "code": "rebuild_unsupported_chunk_lexical",
                "detail": f"Collection {error.collection_id} has chunk-scope lexical field(s) "
                f"{error.fields}: a rebuild would drop their BM25 vectors and nothing refills them. "
                f"Make them document-scope or semantic (or drop lexical), then rebuild.",
                "fields": error.fields,
            },
        )

    @staticmethod
    async def assert_force_cancel_safe(
        database: Database, job: Job, alive_threshold_s: float, now: datetime | None = None
    ) -> None:
        """
        409 ``rebuild_force_cancel_refused`` for a forced cancel of a RUNNING rebuild on a live worker.

        Forcing the row CANCELLED lifts the ingest lock while the copy keeps going; ingests admitted
        then land in the old store the swap deletes. A dead worker (stale/absent heartbeat) copies
        nothing, so the force is safe there.

        Args:
            database (Database): The data façade (heartbeats).
            job (Job): The job being force-cancelled.
            alive_threshold_s (float): A heartbeat fresher than this means the worker is alive.
            now (datetime | None): The reference time (defaults to now, UTC).
        """
        # 1. Only a running rebuild is guarded.
        if job.kind != JobKind.REBUILD_INDEX or job.status != JobStatus.RUNNING:
            return
        # 2. Is the worker that owns it still beating?
        now = now or datetime.now(UTC)
        beat = next(
            (h for h in await database.jobs.list_heartbeats() if h.worker_id == job.worker_id),
            None,
        )
        if beat is None or (now - beat.last_seen).total_seconds() > alive_threshold_s:
            return
        raise HTTPException(
            status_code=409,
            detail={
                "code": "rebuild_force_cancel_refused",
                "detail": f"Job {job.id} is an index rebuild running on live worker "
                f"{job.worker_id}: a forced cancel would lift the ingest lock while the copy "
                f"continues (data loss). Cancel without force — it aborts before the swap.",
                "job_id": str(job.id),
            },
        )

    @classmethod
    async def assert_no_active_rebuild(cls, database: Database, collection_id: uuid.UUID) -> None:
        """Fast pre-check (the facade's FOR SHARE guard is the race-safe one)."""
        job = await database.index_rebuild.active_rebuild(collection_id)
        if job is not None:
            raise cls.active_conflict(IndexRebuildActiveError(collection_id, job.id))

    @staticmethod
    async def assert_index_aligned(database: Database, collection_id: uuid.UUID) -> None:
        """409 ``rebuild_index_required`` when the store lacks a named vector the schema needs."""
        missing = await database.index_state.missing(collection_id)
        if missing:
            vectors = [vector for _, vector in missing]
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rebuild_index_required",
                    "detail": f"The index lacks named vectors {vectors}; a reingest cannot add them "
                    f"— run {REBUILD_ROUTE} first.",
                    "missing_vectors": vectors,
                },
            )

    @classmethod
    async def assert_chunk_vectors_declared(
        cls, database: Database, collection_id: uuid.UUID
    ) -> None:
        """409 ``rebuild_index_required`` before a paid run whose chunk points the store would refuse.

        Only chunk-scope semantic/lexical fields put a ``meta_*`` vector on every chunk point; a
        collection without one is never checked against the store (zero Qdrant call).
        """
        # 1. The chunk-scope searchable surface — nothing to check for a content-only schema.
        schema = await database.collections.get_schema(collection_id)
        chunk_fields = [row for row in schema if row.scope == FieldScope.CHUNK]
        semantic = [row.field_name for row in chunk_fields if row.semantic]
        lexical = [row.field_name for row in chunk_fields if row.lexical]
        if not semantic and not lexical:
            return
        # 2. Compare to the vectors the store declares (a never-ingested store misses nothing).
        missing = await database.index_state.missing_for(collection_id, semantic, lexical)
        if missing:
            raise cls.required_conflict(missing)

    @staticmethod
    def required_conflict(missing: list[tuple[str, str]]) -> HTTPException:
        """409 ``rebuild_index_required`` naming the fields and vectors the store lacks."""
        fields = sorted({field for field, _ in missing})
        vectors = [vector for _, vector in missing]
        return HTTPException(
            status_code=409,
            detail={
                "code": "rebuild_index_required",
                "detail": f"The index lacks named vectors {vectors} for fields {fields}; an "
                f"ingestion cannot add them — run {REBUILD_ROUTE} first.",
                "missing_vectors": vectors,
                "missing_fields": fields,
            },
        )


__all__ = ["IndexRebuildGuards", "REBUILD_ROUTE"]
