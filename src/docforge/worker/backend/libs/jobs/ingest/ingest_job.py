# ====== Code Summary ======
# IngestJob — the orchestrator of the worker's ``ingest_document`` task, one run in pipeline order:
# skip a job that is already terminal, claim it (job RUNNING, document PROCESSING), rehydrate the
# inputs (Rehydrator), then EITHER delegate to the replay run (job.replay_from set at admission) OR
# run the full graph (RunExecutor), translate and persist the delivery (Persister: S3 → Postgres
# one-tx → Qdrant) and close the job DONE. Every non-success ends in the FailureHandler, which owns
# the terminal writes: cooperative cancel (no re-raise), hard cancel (shielded write, then re-raise)
# and any other error (partial tree, both truths FAILED, re-raise so arq accounts the attempt).
# The replay run is injected (never imported) so the ``ingest`` package and replay.py stay acyclic.

# ====== Standard Library Imports ======
import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import JobStatus

# ====== Local Project Imports ======
from ..cancellation import JobCancelledError
from ..stage_plan import StagePlanHelpers
from .failure_handler import FailureHandler
from .ingest_services import IngestServices
from .persister import Persister
from .rehydrated_job import ReplayInputs
from .rehydrator import Rehydrator
from .run_executor import RunExecutor


class IngestJob:
    """Execute one ingestion (or replay) job end to end: claim → rehydrate → run → persist → close."""

    def __init__(
        self,
        services: IngestServices,
        replay_run: Any,
        cache_hook_factory: Callable[..., Any],
    ) -> None:
        """
        Args:
            services (IngestServices): The worker services of this run.
            replay_run (Any): The replay runner class (``ReplayRun``): ``await execute(ReplayInputs)``.
            cache_hook_factory (Callable[..., Any]): ``StageCacheHook`` (see RunExecutor).
        """
        self._services = services
        self._replay_run = replay_run
        self._rehydrator = Rehydrator(services)
        self._executor = RunExecutor(services, cache_hook_factory)
        self._persister = Persister(services)
        self._failures = FailureHandler(services)

    @staticmethod
    def _replay_stage(job: Any) -> str | None:
        """The job's ``replay_from`` stage, or None for a full run (or an unknown job)."""
        replay_from = getattr(job, "replay_from", None)
        return replay_from if isinstance(replay_from, str) and replay_from else None

    async def execute(
        self, ctx: dict[str, Any], document_id: str, job_id: str, force: bool = False
    ) -> None:
        """
        Execute one ingestion end to end: rehydrate → run → translate → persist.

        Args:
            ctx (dict): arq's context dict (``job_try`` is the attempt counter).
            document_id (str): The admitted document's UUID (the queue carries ids only).
            job_id (str): The job row driving the lifecycle/status.
            force (bool): When True, build NO stage-cache hook — a full recompute that reads nothing
                from and writes nothing to the artifact cache (the reingest ``force=true`` path).
        """
        database, logger = self._services.database, self._services.logger
        doc_uuid, job_uuid = uuid.UUID(document_id), uuid.UUID(job_id)

        # Dequeue-skip guard: bail before any work on a job that is ALREADY TERMINAL. Two ways a
        # terminal job reaches the queue — a job cancelled while still queued (marked CANCELLED, its
        # arq task id never captured so it could not be dropped from the queue), and a ZOMBIE arq
        # re-delivery of a job the reaper already marked FAILED (a crashed/SIGTERMed worker's job
        # re-queued by arq). Either way the job is over and its document owns a terminal (or a newer
        # job's) state: re-running it would spuriously fire the cancel guard (the reaper leaves
        # cancel_requested=True) and clobber the document. Skip EVERY terminal status
        # (JobStatus.terminal() — the canonical DONE/FAILED/CANCELLED set), not just CANCELLED, so
        # no zombie retry ever resurrects a finished job.
        existing = await database.jobs.get(job_uuid)
        if existing is not None and existing.status in JobStatus.terminal():
            logger.info(
                f"Skipping already-terminal job {job_id} (status={existing.status.value}, "
                f"document {document_id}) at dequeue"
            )
            return

        # arq's job_try is the attempt counter (1 on first run, increments on retries).
        await database.jobs.mark_running(
            job_uuid,
            worker_id=self._services.worker_id,
            attempt=ctx.get("job_try") or 1,
            started_at=datetime.now(UTC),
        )
        # Flip the DOCUMENT row PENDING → PROCESSING too: mark_running only moves the JOB to RUNNING,
        # so without this the document reads "pending" for the whole run. Guarded to PENDING →
        # PROCESSING, and the terminal DONE/FAILED writes still win.
        await database.ingestion.mark_processing(doc_uuid)
        replay_from = self._replay_stage(existing)
        try:
            # 1. Rehydrate the inputs: rows, original bytes (key = source_hash), contract + blob.
            rehydrated = await self._rehydrator.rehydrate(document_id, doc_uuid, replay_from)

            # 1c. REPLAY mode (job.replay_from set at admission): re-run only that stage and its
            #     downstream on the persisted IR — no intake/parse, downstream-only persistence.
            if replay_from:
                await self._replay_run.execute(
                    ReplayInputs.from_rehydrated(job_uuid, rehydrated, replay_from)
                )
                return

            await self._run_full(document_id, doc_uuid, job_uuid, rehydrated, force)

        except JobCancelledError as exc:
            await self._failures.on_cooperative_cancel(document_id, job_uuid, exc)
            return

        except asyncio.CancelledError:
            await self._failures.on_hard_cancel(document_id, doc_uuid, job_uuid, replay_from)
            raise

        except Exception as exc:
            await self._failures.on_failure(document_id, doc_uuid, job_uuid, replay_from, exc)
            raise

    async def _run_full(
        self,
        document_id: str,
        doc_uuid: uuid.UUID,
        job_uuid: uuid.UUID,
        rehydrated: Any,
        force: bool,
    ) -> None:
        """Steps 2-5 of a full run: progress → run → persist the tree → translate → save → index → DONE."""
        database = self._services.database
        document, collection, blob = rehydrated.document, rehydrated.collection, rehydrated.blob

        # 2. Live progress, over the PLANNED (happy-path) stage subset of the blob.
        guarded_progress = RunExecutor.guarded_progress(
            job_uuid, blob, collection, StagePlanHelpers.planned_stage_ids(blob)
        )

        # 3. Run (fresh input inside), then translate the delivery. The wall-clock job timeout is the
        #    collection's per-collection override when set, else the worker's global default —
        #    fail-fast (before any spend, in the Rehydrator) if the override exceeds arq's hard
        #    ceiling, never truncated.
        cache_hook = self._executor.build_cache_hook(blob, document.collection_id, doc_uuid, force)
        bundle, record = await self._executor.run_full(
            blob,
            rehydrated.source,
            rehydrated.contract,
            timeout_seconds=rehydrated.timeout_seconds,
            progress_callback=guarded_progress,
            trace_level=rehydrated.trace_level,
            cache_hook=cache_hook,
            document_id=document_id,
        )
        await self._persister.persist_execution_tree(job_uuid, record, rehydrated.trace_level)
        translated = self._persister.translate(doc_uuid, bundle, rehydrated.schema, blob)

        # 4. Persist in the safe order: blobs (S3) → the one-tx save (PG) → the vectors (Qdrant),
        # 5. then the best-effort doc-scope denormalisations (shared with the replay path).
        await self._persister.save_full(doc_uuid, translated, bundle)
        await self._persister.index(document.collection_id, doc_uuid, translated)
        await database.jobs.mark_done(job_uuid, finished_at=datetime.now(UTC))


__all__ = ["IngestJob"]
