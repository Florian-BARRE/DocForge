# ====== Code Summary ======
# The asynchronous jobs (the live ingestion status the UI polls) resource: the awaiting shell over
# the shared ``_JobsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.jobs import (
    CancelResult,
    CollectionCost,
    FailureBreakdown,
    JobEventPayload,
    JobPage,
    JobStatus,
    JobTimeseries,
    JobTrace,
    NewFailures,
    QueueDepth,
    StageDurations,
    WorkersLive,
)
from .._base import AsyncResource
from .specs import _JobsSpecs


class AsyncJobs(AsyncResource, _JobsSpecs):
    """Asynchronous ingestion-job monitoring."""

    async def list(
        self,
        collection_id: str | None = None,
        status: list[str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        *,
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort: str | None = None,
    ) -> JobPage:
        """
        List one bounded page of jobs — a collection's, or (with no ``collection_id``) the fleet's.

        Args:
            collection_id (str | None): Scope to one collection. Omitted → a FLEET-WIDE listing
                (full-access keys only) — the "All Jobs" view.
            status (list[str] | None): Filter to these statuses (pending/running/done/failed/
                cancelled). Omitted → all statuses.
            order (str | None): Sort direction — ``newest`` (default, DESC) or ``oldest`` (ASC —
                FIFO/"what runs next", typically with ``status=['pending']``).
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            offset (int | None): Rows to skip for paging (default 0).
            stage (str | None): Filter to jobs in this stage. Omitted → all stages.
            error_type (str | None): Filter to jobs with this failure class. Omitted → all.
            search (str | None): Prefix-match the job id OR document id. Omitted → no id search.
            created_after (str | None): Keep jobs created at/after this ISO-8601 instant.
            created_before (str | None): Keep jobs created at/before this ISO-8601 instant.
            sort (str | None): Sort dimension — ``created`` (default), ``duration`` or ``status``.

        Returns:
            JobPage: The page (``.jobs``) plus ``total``/``limit``/``offset`` for pagination.
        """
        return await self._transport.request(
            self._list_spec(
                collection_id,
                status,
                order,
                limit,
                offset,
                stage=stage,
                error_type=error_type,
                search=search,
                created_after=created_after,
                created_before=created_before,
                sort=sort,
            ),
            JobPage,
        )

    async def failure_breakdown(
        self, collection_id: str | None = None, window_hours: int | None = None
    ) -> FailureBreakdown:
        """
        Aggregate recent failures by cause / stage / collection over a window — the "why it breaks" panel.

        Args:
            collection_id (str | None): Scope to one collection. Omitted → fleet-wide (full-access).
            window_hours (int | None): Look-back window in hours (server default 24, max 720).

        Returns:
            FailureBreakdown: The window total and the three descending, bounded groupings.
        """
        return await self._transport.request(
            self._failure_breakdown_spec(collection_id, window_hours), FailureBreakdown
        )

    async def new_failures(
        self,
        since: str,
        collection_id: str | None = None,
        include_ids: bool | None = None,
        limit: int | None = None,
    ) -> NewFailures:
        """
        Count jobs that have failed since a cursor — the "X new failures since you last looked" signal.

        Args:
            since (str): The last-seen cursor (ISO-8601) — only failures finished after it count.
            collection_id (str | None): Scope to one collection. Omitted → fleet-wide (full-access).
            include_ids (bool | None): Also return the bounded list of new-failure ids.
            limit (int | None): Maximum ids returned when ``include_ids`` is set (server default 50).

        Returns:
            NewFailures: The count, the newest failure time (next cursor), and the optional ids.
        """
        return await self._transport.request(
            self._new_failures_spec(since, collection_id, include_ids, limit), NewFailures
        )

    async def timeseries(
        self, collection_id: str | None = None, window_hours: int | None = None
    ) -> JobTimeseries:
        """
        Fetch lightweight hourly job trends (done/failed/arrivals/backlog) — the in-product sparklines.

        Args:
            collection_id (str | None): Scope to one collection. Omitted → fleet-wide (full-access).
            window_hours (int | None): Hours of history as hourly buckets (server default 24, max 168).

        Returns:
            JobTimeseries: The contiguous hourly series (oldest bucket first).
        """
        return await self._transport.request(
            self._timeseries_spec(collection_id, window_hours), JobTimeseries
        )

    async def get(self, job_id: str) -> JobStatus:
        """
        Fetch one job's live status.

        Args:
            job_id (str): The job's UUID.

        Returns:
            JobStatus: The job's current state.
        """
        return await self._transport.request(self._get_spec(job_id), JobStatus)

    async def get_events(self, job_id: str) -> JobTrace:
        """
        Fetch a job's per-node execution trace, in run order.

        Args:
            job_id (str): The job's UUID.

        Returns:
            JobTrace: The ordered per-node trace.
        """
        return await self._transport.request(self._get_events_spec(job_id), JobTrace)

    async def get_event_payload(
        self, job_id: str, event_id: str, slot: str = "output"
    ) -> JobEventPayload:
        """
        Fetch one stage-event's full raw input or output payload (opt-in ``full`` trace tier).

        Args:
            job_id (str): The job's UUID.
            event_id (str): The stage-event row's UUID (JobEvent.event_id).
            slot (str): Which side to fetch — "input" or "output" (default "output").

        Returns:
            JobEventPayload: The node's full raw payload for the requested slot.
        """
        return await self._transport.request(
            self._get_event_payload_spec(job_id, event_id, slot), JobEventPayload
        )

    async def live_workers(self) -> WorkersLive:
        """
        Fetch everything running right now, grouped by worker.

        Returns:
            WorkersLive: The live per-worker activity view.
        """
        return await self._transport.request(self._live_workers_spec(), WorkersLive)

    async def cancel(self, job_id: str, force: bool = False) -> CancelResult:
        """
        Cancel an ingestion job — cooperatively for a running job, immediately for a queued or
        wedged one.

        Args:
            job_id (str): The job's UUID.
            force (bool): Immediately terminate a running/wedged job regardless of worker state
                instead of asking it to stop cooperatively at its next stage boundary.

        Returns:
            CancelResult: The job's post-call status, whether a cooperative stop is pending, and
            the outcome.
        """
        return await self._transport.request(self._cancel_spec(job_id, force), CancelResult)

    async def cost(self, collection_id: str) -> CollectionCost:
        """The collection's paid text-gen roll-up — tokens + USD summed over its documents' jobs."""
        return await self._transport.request(self._cost_spec(collection_id), CollectionCost)

    async def queue(self, collection_id: str | None = None) -> QueueDepth:
        """Backlog counters (pending/running) — fleet-wide (root) or for one collection."""
        return await self._transport.request(self._queue_spec(collection_id), QueueDepth)

    async def stage_durations(self, collection_id: str) -> StageDurations:
        """Average per-stage wall-clock over the collection's done jobs (a running job's ETA basis)."""
        return await self._transport.request(
            self._stage_durations_spec(collection_id), StageDurations
        )
