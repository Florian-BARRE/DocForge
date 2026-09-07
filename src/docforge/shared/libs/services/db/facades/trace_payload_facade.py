# ====== Code Summary ======
# TracePayloadFacade — the READ + LIFECYCLE surface for the full execution-trace payloads the worker
# stores in the object store (the opt-in ``trace_verbosity='full'`` tier). The WRITE side lives on
# IngestionFacade (the worker persistence path); this façade serves one node's full payload on demand
# (the app's fetch route), purges a run's whole payload namespace by job prefix (the deletion/reingest
# hooks), and runs the retention GC (age out old jobs' payloads). Postgres addresses the row + carries
# the refs; S3 holds the bytes. Purge/GC are best-effort by contract — they must never fail a delete.

# ====== Standard Library Imports ======
import json
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.s3 import S3Client, S3ObjectApi

# ====== Local Project Imports ======
from .trace_payloads import TracePayloadRead
from .trace_purge import TracePurgeHelper

# The two addressable trace slots — a node's resolved input and its produced output.
_SLOT_REFS = {"input": "input_ref", "output": "output_ref"}
_SLOT_FLAGS = {"input": "has_full_input", "output": "has_full_output"}


class TracePayloadFacade(LoggerClass):
    """Read one node's full trace payload, purge a run's payloads, and age them out (retention GC)."""

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    async def read_payload(
        self, job_id: uuid.UUID, event_id: uuid.UUID, slot: str, max_bytes: int
    ) -> TracePayloadRead:
        """
        Fetch ONE stage-event node's full raw payload for a slot, from the object store.

        The trace list carries only the cheap shape summaries; this serves the FULL payload one slot
        at a time so a heavy IR is never inlined. The row is addressed by (job_id, event_id) — the job
        is AND-ed into the lookup so an event id can never be read under the wrong job. A row that only
        carried a shape summary (or whose payload was aged/purged, clearing its ref) reads
        ``has_full=False`` → a typed 404 at the router, never a 500. The object is size-probed first and
        skipped (``truncated=True``, no body) when it exceeds ``max_bytes``.

        Args:
            job_id (uuid.UUID): The job the node belongs to (the scope gate is enforced on it upstream).
            event_id (uuid.UUID): The stage-event row's id.
            slot (str): Which side to read — ``input`` or ``output``.
            max_bytes (int): Read cap; a stored object larger than this is reported truncated, not read.

        Returns:
            TracePayloadRead: found/has_full flags + (when available) the parsed payload and its size.
        """
        # 1. Resolve the addressed trace row (scoped to the job) — an unknown id is a clean not-found.
        async with self._postgres.session() as session:
            event = await JobApi.get_event(session, job_id, event_id)
        if event is None:
            return TracePayloadRead(found=False)

        # 2. Pick the slot's ref + availability flag; a shape-only row (no ref / flag false) is a
        #    "row exists but no full payload" — the router turns this into a typed 404.
        ref = getattr(event, _SLOT_REFS[slot])
        has_full = bool(getattr(event, _SLOT_FLAGS[slot]))
        if ref is None or not has_full:
            return TracePayloadRead(
                found=True, has_full=False, stage=event.stage, node_path=event.node_path
            )

        # 3. Size-probe, then read the bytes under the cap and parse the JSON payload. A ref pointing at
        #    an object that is genuinely gone (a dangling ref) is treated as unavailable, not a 500.
        async with self._s3.client() as s3:
            try:
                size = await S3ObjectApi.head_size(s3, self._s3.bucket, ref)
            except s3.exceptions.NoSuchKey:
                return TracePayloadRead(
                    found=True, has_full=False, stage=event.stage, node_path=event.node_path
                )
            if size > max_bytes:
                return TracePayloadRead(
                    found=True,
                    has_full=True,
                    stage=event.stage,
                    node_path=event.node_path,
                    truncated=True,
                    size_bytes=size,
                )
            raw = await S3ObjectApi.get(s3, self._s3.bucket, ref)
        return TracePayloadRead(
            found=True,
            has_full=True,
            stage=event.stage,
            node_path=event.node_path,
            payload=json.loads(raw),
            size_bytes=size,
        )

    async def purge_jobs(self, job_ids: Sequence[uuid.UUID]) -> int:
        """
        Purge every trace payload of the given jobs — the deletion/reingest hook and the GC's worker.

        Two best-effort steps that must NEVER fail a delete: first the DB refs on those jobs' rows are
        cleared (so no surviving row — e.g. a reingested document's OLD job, whose rows are NOT
        cascade-deleted — advertises a payload that is about to vanish), then each job's
        ``trace/{job_id}/`` object-store namespace is prefix-deleted. A per-job store error is logged
        and skipped so one bad job never aborts a bulk purge.

        Args:
            job_ids (Sequence[uuid.UUID]): The jobs whose full-trace payloads are reclaimed.

        Returns:
            int: The number of object-store objects deleted across all jobs.
        """
        return await TracePurgeHelper.purge(self._postgres, self._s3, job_ids)

    async def gc_before(self, cutoff: datetime, batch_size: int) -> int:
        """
        Age out stored full-trace payloads: purge the object-store space of jobs older than ``cutoff``.

        The retention pass, driven off job age (keys are job-prefixed). One bounded batch of eligible
        jobs (created before the cutoff and still carrying stored payloads) is resolved, then purged
        via ``purge_jobs`` (which also clears their refs, so the pass converges — a purged job no
        longer matches on the next run). Returns the number of jobs purged this call.

        Args:
            cutoff (datetime): Jobs created strictly before this have their trace payloads reclaimed.
            batch_size (int): The maximum number of jobs to purge in one call.

        Returns:
            int: The number of jobs whose payloads were purged (0 when none were old enough).
        """
        async with self._postgres.session() as session:
            job_ids = await JobApi.list_trace_job_ids_before(session, cutoff, batch_size)
        if not job_ids:
            return 0
        await self.purge_jobs(job_ids)
        return len(job_ids)


__all__ = ["TracePayloadFacade"]
