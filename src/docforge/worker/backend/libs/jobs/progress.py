# ====== Code Summary ======
# JobProgressRecorder — turns the engine's per-node progress events into the job's LIVE state. On a
# root stage START it OPENS a stage-event row (status "running") and marks the job's current_stage;
# on END it FINALIZES that row (status + timestamps + duration/error + token/cost) and advances the
# coarse percentage. Opening the row at START is what lets a run cut mid-stage (timeout/cancel/reaper)
# be closed as a red row on the exact stage it died in, instead of an all-green trace with a gap.
# For a fan-out (foreach) root it also maintains a live per-item counter (items_done / items_total) by
# counting the body ENTRY node's END events — the one node every item runs — without persisting the
# per-item tree. The counter resets to NULL when the job enters a non-fan-out stage.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ForEach
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.services.db.postgresql.tables import JobStageEvent

# ====== Local Project Imports ======
from .usage import StageUsageSummer


class JobProgressRecorder(LoggerClass):
    """One instance per run — the engine's progress callback, writing the job's live state."""

    def __init__(
        self,
        job_id: uuid.UUID,
        root_node_ids: list[str],
        planned_stage_ids: list[str] | None = None,
        rates: RateTable | None = None,
    ) -> None:
        """
        Args:
            job_id (uuid.UUID): The job row to keep live.
            root_node_ids (list[str]): EVERY top-level node id — the stages that may be TRACED. Kept
                whole (escalation/fallback steps included) so a step that does run still opens and
                closes its stage row.
            planned_stage_ids (list[str] | None): The top-level stages a successful run actually
                walks — the progress DENOMINATOR. Excludes escalation/fallback steps that run only on
                a bad outcome, so the percentage is not understated by never-run nodes. Defaults to
                ``root_node_ids`` (every stage) when not supplied.
            rates (RateTable | None): The collection's effective rate table (defaults folded with its
                per-collection rate overrides) the per-stage cost meter prices against — so actual
                spend matches the estimate. Defaults to the canonical ``RateTable.default()``.
        """
        LoggerClass.__init__(self)
        self._job_id = job_id
        self._rates = rates if rates is not None else RateTable.default()
        self._roots = set(root_node_ids)
        denominator = planned_stage_ids if planned_stage_ids is not None else root_node_ids
        self._total = max(1, len(denominator))
        self._done = 0
        self._started: dict[str, datetime] = {}
        # The stage-event row opened at the current root stage's START, finalized at its END.
        self._open_event_id: uuid.UUID | None = None
        self._open_stage: str | None = None
        # Live fan-out counter state for the CURRENT foreach root (None when not in a fan-out).
        self._fanout_root: str | None = None
        self._fanout_entry: str | None = None
        self._items_done = 0
        self._items_total: int | None = None
        # Whether the job's item counter currently holds a value — avoids a redundant reset write.
        self._items_active = False

    async def __call__(self, event: ProgressEvent) -> None:
        """
        Handle one engine progress event (the engine awaits this between nodes).

        Args:
            event (ProgressEvent): START or END of one node, with its record on END.
        """
        # 1. Root stages drive the trace + percentage; nested events only feed the fan-out counter.
        if event.node_id in self._roots:
            if event.phase == ProgressPhase.START:
                await self.__start_stage(event)
            else:
                await self.__end_stage(event)
            return
        await self.__count_item(event)

    def __percentage(self) -> int:
        """Coarse 0-99 completion from finished root stages (100 is reserved for mark_done)."""
        return min(99, int(self._done * 100 / self._total))

    async def __start_stage(self, event: ProgressEvent) -> None:
        """Open a running stage-event row and set the job's current stage + item counter."""
        now = datetime.now(UTC)
        node_id = event.node_id

        # 1. Fan-out counter: a foreach root arms the counter (its START carries the item total); any
        #    other root leaves a fan-out and resets the counter to NULL.
        if event.kind == ForEach.KIND:
            self._fanout_root = node_id
            self._fanout_entry = None
            self._items_done = 0
            self._items_total = event.total_items
            self._items_active = True
            await CONTEXT.database.jobs.set_items(self._job_id, 0, event.total_items)
        else:
            self._fanout_root = None
            self._fanout_entry = None
            self._items_total = None
            self._items_done = 0
            if self._items_active:
                await CONTEXT.database.jobs.set_items(self._job_id, None, None)
                self._items_active = False

        # 2. Open the stage-event row (finalized at END; closed as failed if the run is cut first).
        self._started[node_id] = now
        row = await CONTEXT.database.jobs.record_event(
            JobStageEvent(
                job_id=self._job_id,
                stage=node_id,
                status="running",
                node_kind=event.kind,
                started_at=now,
                finished_at=None,
            )
        )
        self._open_event_id = row.id
        self._open_stage = node_id

        # 3. The job row shows what is running NOW.
        await CONTEXT.database.jobs.set_progress(
            self._job_id, current_stage=node_id, progress=self.__percentage()
        )

    async def __count_item(self, event: ProgressEvent) -> None:
        """Advance the fan-out counter: one END of the body's entry node = one item processed."""
        if self._fanout_root is None:
            return
        # The body's ENTRY node is the FIRST nested node to START — it runs once per item, so its END
        # count is a monotonic, topology-free items-done signal (bounded by items_total).
        if event.phase == ProgressPhase.START:
            if self._fanout_entry is None:
                self._fanout_entry = event.node_id
            return
        if event.node_id == self._fanout_entry:
            self._items_done += 1
            await CONTEXT.database.jobs.set_items(self._job_id, self._items_done, self._items_total)

    async def __end_stage(self, event: ProgressEvent) -> None:
        """Finalize the stage's open row (status + duration/error + usage) and advance progress."""
        now = datetime.now(UTC)
        node_id = event.node_id
        self._done += 1
        record = event.record
        status = record.status.value if record else "success"
        if record and record.error:
            detail: str | None = f"{record.error.error_type}: {record.error.message}"
        elif record:
            detail = f"{record.duration_ms:.0f} ms"
        else:
            detail = None

        # 1. Total this stage's paid text-gen usage over its whole execution tree, priced per leaf.
        prompt_tokens, completion_tokens, cost_usd, usage_count = (
            StageUsageSummer.summarize(record, self._rates) if record else (0, 0, None, 0)
        )
        has_usage = usage_count > 0
        cost_column = Decimal(str(cost_usd)) if (has_usage and cost_usd is not None) else None

        # 2. Finalize the row opened at START; fall back to a fresh row if this stage never opened
        #    one (a foreach that failed before it could announce its START).
        self._started.pop(node_id, None)
        if self._open_event_id is not None and self._open_stage == node_id:
            await CONTEXT.database.jobs.finalize_event(
                self._open_event_id,
                status,
                now,
                detail,
                prompt_tokens if has_usage else None,
                completion_tokens if has_usage else None,
                cost_column,
            )
            self._open_event_id = None
            self._open_stage = None
        else:
            await CONTEXT.database.jobs.record_event(
                JobStageEvent(
                    job_id=self._job_id,
                    stage=node_id,
                    status=status,
                    node_kind=event.kind,
                    finished_at=now,
                    detail=detail,
                    prompt_tokens=prompt_tokens if has_usage else None,
                    completion_tokens=completion_tokens if has_usage else None,
                    cost_usd=cost_column,
                )
            )

        # 3. Advance the percentage, fold usage into the job meter, and close the fan-out window.
        await CONTEXT.database.jobs.set_progress(
            self._job_id, current_stage=node_id, progress=self.__percentage()
        )
        if has_usage:
            await CONTEXT.database.jobs.add_usage(
                self._job_id, prompt_tokens, completion_tokens, cost_usd
            )
        if self._fanout_root == node_id:
            self._fanout_root = None
            self._fanout_entry = None


__all__ = ["JobProgressRecorder"]
