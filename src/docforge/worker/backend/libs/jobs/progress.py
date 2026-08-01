# ====== Code Summary ======
# JobProgressRecorder — turns the engine's per-node progress events into the job's LIVE state:
# on START the job row shows which node is running NOW (current_stage); on END the global
# percentage advances and ONE JobStageEvent trace row lands (stage, status, both timestamps,
# duration or error detail). Only ROOT nodes are traced — per-item events inside a foreach
# (hundreds of figures) would flood the trace table without adding stage-level meaning.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase
from shared_libs.pipelines.nodes.openai_compat import price_usd
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

        # 4. Total this stage's paid text-gen usage from its whole execution tree (per-figure VLM
        #    calls are nested child records), priced per leaf, then land it on the trace row and fold
        #    it into the job's per-document meter. No usage → NULL columns, no increment.
        prompt_tokens, completion_tokens, cost_usd, usage_count = (
            self._sum_usage(record) if record else (0, 0, None, 0)
        )
        has_usage = usage_count > 0

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
                prompt_tokens=prompt_tokens if has_usage else None,
                completion_tokens=completion_tokens if has_usage else None,
                cost_usd=(Decimal(str(cost_usd)) if (has_usage and cost_usd is not None) else None),
            )
        )
        if has_usage:
            await CONTEXT.database.jobs.add_usage(
                self._job_id, prompt_tokens, completion_tokens, cost_usd
            )

    @classmethod
    def _sum_usage(cls, record: NodeExecutionRecord) -> tuple[int, int, float | None, int]:
        """
        Total a stage's paid-call usage over its execution tree, priced per leaf.

        Only leaf action records carry ``usage`` (groups/foreach wrappers do not), and a stage may
        fan out over MIXED models (a foreach whose items escalated to different providers), so each
        leaf is priced individually and the costs summed — never a single-model assumption. Cost is
        None when NO leaf's model is priceable (the UI shows tokens but a "—" cost) rather than a
        fabricated zero; the summed cost otherwise (unpriceable leaves contribute tokens, no cost).

        Args:
            record (NodeExecutionRecord): The stage's record (recursed into its children).

        Returns:
            tuple[int, int, float | None, int]: (prompt tokens, completion tokens, USD cost or None,
                number of leaves that carried usage).
        """
        prompt = 0
        completion = 0
        cost = 0.0
        priced = False
        usage_count = 0

        if record.usage is not None:
            usage = record.usage
            prompt += usage.prompt_tokens
            completion += usage.completion_tokens
            usage_count += 1
            leaf_cost = price_usd(usage.model, usage.prompt_tokens, usage.completion_tokens)
            if leaf_cost is not None:
                cost += leaf_cost
                priced = True

        for child in record.children:
            child_prompt, child_completion, child_cost, child_count = cls._sum_usage(child)
            prompt += child_prompt
            completion += child_completion
            usage_count += child_count
            if child_cost is not None:
                cost += child_cost
                priced = True

        return prompt, completion, (cost if priced else None), usage_count


__all__ = ["JobProgressRecorder"]
