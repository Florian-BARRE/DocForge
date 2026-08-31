# ====== Code Summary ======
# The worker-side cooperative-cancel hook. CancellationGuard decorates the run's progress callback:
# at each ROOT stage boundary (a node's START) it re-reads the job's cancel flag from the DB and, if
# a cancellation was requested, raises JobCancelledError to abort the run BEFORE the next stage opens
# — then forwards the event to the wrapped recorder. This is edge/orchestration (a cheap DB re-read
# between nodes), never node logic, so pipeline purity is preserved.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import ProgressCallback, ProgressEvent, ProgressPhase


class JobCancelledError(Exception):
    """Raised inside the run when a cooperative cancellation is observed at a stage boundary.

    Caught by the ingest task to mark the job + document CANCELLED (never FAILED) and stop WITHOUT
    re-raising, so arq does not retry a job the operator explicitly stopped.
    """


class CancellationGuard(LoggerClass):
    """
    Decorates the run's progress callback with a between-stages cooperative-cancel check.

    Wraps the inner progress callback (the JobProgressRecorder): every event is forwarded to it, but
    at the START of a ROOT stage the guard first re-reads the job's ``cancel_requested`` flag and,
    when set, raises ``JobCancelledError`` so the run stops at the stage boundary — before the next
    stage opens its work. The check is scoped to root stages (the traced boundaries) to keep it a
    single cheap read per stage rather than per nested node.
    """

    def __init__(
        self, job_id: uuid.UUID, root_node_ids: list[str], inner: ProgressCallback
    ) -> None:
        """
        Args:
            job_id (uuid.UUID): The job whose cancel flag is probed.
            root_node_ids (list[str]): The blob's top-level node ids — the stage boundaries checked.
            inner (ProgressCallback): The wrapped callback (the live-status recorder) events forward to.
        """
        LoggerClass.__init__(self)
        self._job_id = job_id
        self._roots = set(root_node_ids)
        self._inner = inner

    async def __call__(self, event: ProgressEvent) -> None:
        """
        Probe the cancel flag at a root stage boundary, then forward the event to the recorder.

        Args:
            event (ProgressEvent): The engine's START/END event for one node.

        Raises:
            JobCancelledError: A cooperative cancellation was requested (checked at a root START).
        """
        # 1. Between-stages guard: a root node's START is the honoured cancellation boundary.
        if event.phase == ProgressPhase.START and event.node_id in self._roots:
            if await CONTEXT.database.jobs.is_cancel_requested(self._job_id):
                self.logger.info(
                    f"Job {self._job_id} cancellation honoured at stage boundary '{event.node_id}'"
                )
                raise JobCancelledError(f"cancelled at stage boundary before '{event.node_id}'")

        # 2. Not cancelled — the live-status recorder handles the event as usual.
        await self._inner(event)


__all__ = ["JobCancelledError", "CancellationGuard"]
