# ====== Code Summary ======
# JobProgressRecorder — turns the engine's per-node progress events into the job's LIVE state:
# on START the job row shows which node is running NOW (current_stage); on END the global
# percentage advances and ONE JobStageEvent trace row lands (stage, status, both timestamps,
# duration or error detail). Only ROOT nodes are traced — per-item events inside a foreach
# (hundreds of figures) would flood the trace table without adding stage-level meaning.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase
from shared_libs.services.db.postgresql.tables import JobStageEvent


class JobProgressRecorder(LoggerClass):
    """One instance per run — the engine's progress callback, writing the job's live state."""

    def __init__(self, job_id: uuid.UUID, root_node_ids: list[str]) -> None:
        """
        Args:
            job_id (uuid.UUID): The job row to keep live.
            root_node_ids (list[str]): The blob's top-level node ids — the traced stages.
        """
        LoggerClass.__init__(self)
        self._job_id = job_id
        self._roots = set(root_node_ids)
        self._total = max(1, len(root_node_ids))
        self._done = 0
        self._started: dict[str, datetime] = {}

    async def __call__(self, event: ProgressEvent) -> None:
        """
        Handle one engine progress event (the engine awaits this between nodes).

        Args:
            event (ProgressEvent): START or END of one node, with its record on END.
        """
        # 1. Per-item / nested events stay out of the stage trace.
        if event.node_id not in self._roots:
            return
        now = datetime.now(UTC)

        # 2. START: the job row shows what is running NOW.
        if event.phase == ProgressPhase.START:
            self._started[event.node_id] = now
            await CONTEXT.database.jobs.set_progress(
                self._job_id,
                current_stage=event.node_id,
                progress=min(99, int(self._done * 100 / self._total)),
            )
            return

        # 3. END: advance the percentage and land the trace row (status + duration or error).
        self._done += 1
        record = event.record
        status = record.status.value if record else "success"
        if record and record.error:
            detail = f"{record.error.error_type}: {record.error.message}"
        elif record:
            detail = f"{record.duration_ms:.0f} ms"
        else:
            detail = None
        await CONTEXT.database.jobs.set_progress(
            self._job_id,
            current_stage=event.node_id,
            progress=min(99, int(self._done * 100 / self._total)),
        )
        await CONTEXT.database.jobs.record_event(
            JobStageEvent(
                job_id=self._job_id,
                stage=event.node_id,
                status=status,
                started_at=self._started.pop(event.node_id, None),
                finished_at=now,
                detail=detail,
            )
        )


__all__ = ["JobProgressRecorder"]
