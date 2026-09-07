# ====== Code Summary ======
# TracePurgeHelper — the single best-effort routine that reclaims a set of jobs' full execution-trace
# payloads: clear the DB refs on those jobs' stage-event rows (so a surviving row never advertises a
# payload that is gone), then prefix-delete each job's ``trace/{job_id}/`` object-store namespace. It
# takes the store clients as arguments so BOTH the TracePayloadFacade (read/GC surface) and the
# deletion facades (document/collection delete, reingest) share ONE implementation without a façade
# cross-call. Best-effort by contract — every failure is logged and swallowed, never propagated, so a
# purge can never fail the delete it rides behind.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class TracePurgeHelper:
    """Static best-effort purge of a set of jobs' full-trace payloads (DB refs + object-store bytes)."""

    logger = loggerplusplus.bind(identifier="TracePurgeHelper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TracePurgeHelper is a static-only class and cannot be instantiated.")

    @classmethod
    async def purge(
        cls,
        postgres: PostgresClient,
        s3: S3Client,
        job_ids: Sequence[uuid.UUID],
    ) -> int:
        """
        Reclaim the trace payloads of the given jobs — clear their refs, then prefix-delete the bytes.

        Two best-effort steps that NEVER raise: first the DB refs on those jobs' stage-event rows are
        cleared (a reingested document keeps its OLD job's rows, so a stale ref would otherwise dangle
        after the bytes vanish), then each job's ``trace/{job_id}/`` object-store namespace is
        prefix-deleted. Any failure is logged and swallowed so the caller's delete is never blocked.

        Args:
            postgres (PostgresClient): The tabular store (to clear the rows' refs).
            s3 (S3Client): The object store (to prefix-delete the payload bytes).
            job_ids (Sequence[uuid.UUID]): The jobs whose payloads are reclaimed (empty → no-op).

        Returns:
            int: The number of object-store objects deleted across all jobs.
        """
        job_ids = list(job_ids)
        if not job_ids:
            return 0
        # 1. Clear the DB refs first (best-effort) so no surviving row points at bytes about to vanish.
        try:
            async with postgres.session() as session:
                await JobApi.clear_trace_refs(session, job_ids)
        except Exception as exc:  # best-effort: a ref-clear failure must never block the delete.
            cls.logger.warning(f"Trace ref-clear failed for {len(job_ids)} job(s): {exc}")
        # 2. Prefix-delete each job's object-store namespace, per-job best-effort.
        deleted = 0
        try:
            async with s3.client() as client:
                for job_id in job_ids:
                    try:
                        deleted += await S3ObjectApi.delete_prefix(
                            client, s3.bucket, DatabaseHelpers.trace_prefix(job_id)
                        )
                    except Exception as exc:  # one bad job never aborts the batch.
                        cls.logger.warning(f"Trace payload purge failed for job {job_id}: {exc}")
        except Exception as exc:  # a broken client scope must not fail the delete either.
            cls.logger.warning(f"Trace payload purge could not open the object store: {exc}")
        return deleted


__all__ = ["TracePurgeHelper"]
