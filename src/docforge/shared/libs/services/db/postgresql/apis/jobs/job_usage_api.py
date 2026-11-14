# ====== Code Summary ======
# JobUsageApi — Token / cost metering of jobs: fold a stage's usage into the job totals, average
# per-stage durations, and roll a collection's meters up.

# ====== Standard Library Imports ======
import uuid
from decimal import Decimal

# ====== Third-Party Library Imports ======
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Job,
    JobStageEvent,
    JobStatus,
)


class JobUsageApi:
    """Static data-access API: token / cost metering and per-stage duration averages."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobUsageApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def add_usage(
        session: AsyncSession,
        job_id: uuid.UUID,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """
        Atomically fold a stage's token/cost usage into the job's running per-document totals.

        Null-safe: an unknown-model stage (``cost_usd=None``) still adds its tokens but zero cost,
        so an unpriceable call never fabricates a number. Done as an in-place ``UPDATE ... SET col =
        col + :delta`` so concurrent stage ends never lose an increment.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose meter advances.
            prompt_tokens (int): Input tokens to add.
            completion_tokens (int): Output tokens to add.
            cost_usd (float | None): USD cost to add (None contributes 0).
        """
        cost = Decimal(str(cost_usd)) if cost_usd is not None else Decimal(0)
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                total_prompt_tokens=Job.total_prompt_tokens + prompt_tokens,
                total_completion_tokens=Job.total_completion_tokens + completion_tokens,
                cost_usd=Job.cost_usd + cost,
            )
        )

    @staticmethod
    async def avg_stage_durations(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> dict[str, float]:
        """
        Average per-stage wall-clock duration (seconds) over the collection's DONE jobs.

        Feeds the UI's remaining-time estimate for a running job (it sums the not-yet-finished
        stages). Only events with BOTH timestamps count; a stage with no completed sample is absent.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection whose jobs' events are averaged.

        Returns:
            dict[str, float]: Stage id → average duration in seconds.
        """
        result = await session.execute(
            select(
                JobStageEvent.stage,
                func.avg(
                    func.extract("epoch", JobStageEvent.finished_at - JobStageEvent.started_at)
                ),
            )
            .join(Job, Job.id == JobStageEvent.job_id)
            .where(
                Job.collection_id == collection_id,
                Job.status == JobStatus.DONE,
                JobStageEvent.started_at.is_not(None),
                JobStageEvent.finished_at.is_not(None),
            )
            .group_by(JobStageEvent.stage)
        )
        return {stage: float(avg) for stage, avg in result.all() if avg is not None}

    @staticmethod
    async def collection_cost(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> tuple[int, int, float, int]:
        """
        Roll up the collection's per-document meters into one total.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection to total.

        Returns:
            tuple[int, int, float, int]: (total prompt tokens, total completion tokens, total USD
                cost, document/job count) — all zero for a collection with no jobs.
        """
        result = await session.execute(
            select(
                func.coalesce(func.sum(Job.total_prompt_tokens), 0),
                func.coalesce(func.sum(Job.total_completion_tokens), 0),
                func.coalesce(func.sum(Job.cost_usd), 0),
                func.count(Job.id),
            ).where(Job.collection_id == collection_id)
        )
        prompt, completion, cost, count = result.one()
        return int(prompt), int(completion), float(cost), int(count)


__all__ = ["JobUsageApi"]
