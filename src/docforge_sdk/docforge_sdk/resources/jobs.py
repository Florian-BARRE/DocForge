# ====== Code Summary ======
# The jobs resource — the live ingestion status the UI polls. All URL/param logic lives once in the
# pure _JobsSpecs mixin so AsyncJobs and SyncJobs differ ONLY by ``await``. The collection filter on
# the list endpoint is a query parameter (not a path segment), threaded through the spec's params.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.jobs import (
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
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _JobsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the jobs endpoints — the single source of URL/param logic."""

    _JOBS_PATH = "/jobs"

    def _list_spec(
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
    ) -> RequestSpec:
        """
        Build the spec for listing jobs (a bounded, paginated, triageable page) — scoped or fleet-wide.

        Args:
            collection_id (str | None): Scope to one collection (a QUERY parameter). Omitted → a
                FLEET-WIDE listing (full-access keys only) — the "All Jobs" view.
            status (list[str] | None): Filter to these job statuses (pending/running/done/failed/
                cancelled), passed as a repeated query param. Omitted → all statuses.
            order (str | None): Sort DIRECTION — ``newest`` (DESC, the default) or ``oldest`` (ASC —
                FIFO/"what runs next"). Omitted → the server default (newest).
            limit (int | None): Page size; the server clamps it to its ceiling. Omitted → the
                server default (its ceiling).
            offset (int | None): Rows to skip for paging. Omitted → 0.
            stage (str | None): Filter to jobs in this stage (current_stage). Omitted → all stages.
            error_type (str | None): Filter to jobs with this structured failure class. Omitted → all.
            search (str | None): Prefix-match the job id OR document id. Omitted → no id search.
            created_after (str | None): Keep jobs created at/after this ISO-8601 instant.
            created_before (str | None): Keep jobs created at/before this ISO-8601 instant.
            sort (str | None): Sort dimension — ``created`` (default), ``duration`` or ``status``.

        Returns:
            RequestSpec: A GET on the jobs collection with the optional triage filters / sort / paging.
        """
        params: dict[str, object] = {}
        if collection_id is not None:
            params["collection_id"] = collection_id
        if status is not None:
            params["status"] = status
        if order is not None:
            params["order"] = order
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if stage is not None:
            params["stage"] = stage
        if error_type is not None:
            params["error_type"] = error_type
        if search is not None:
            params["search"] = search
        if created_after is not None:
            params["created_after"] = created_after
        if created_before is not None:
            params["created_before"] = created_before
        if sort is not None:
            params["sort"] = sort
        return RequestSpec("GET", self._JOBS_PATH, params=params or None)

    def _failure_breakdown_spec(
        self, collection_id: str | None = None, window_hours: int | None = None
    ) -> RequestSpec:
        """A GET of the failure-breakdown panel (top causes / by stage / by collection over a window)."""
        params: dict[str, object] = {}
        if collection_id is not None:
            params["collection_id"] = collection_id
        if window_hours is not None:
            params["window_hours"] = window_hours
        return RequestSpec("GET", f"{self._JOBS_PATH}/failures/breakdown", params=params or None)

    def _new_failures_spec(
        self,
        since: str,
        collection_id: str | None = None,
        include_ids: bool | None = None,
        limit: int | None = None,
    ) -> RequestSpec:
        """A GET of the "new failures since a cursor" signal (count + optional bounded ids)."""
        params: dict[str, object] = {"since": since}
        if collection_id is not None:
            params["collection_id"] = collection_id
        if include_ids is not None:
            params["include_ids"] = include_ids
        if limit is not None:
            params["limit"] = limit
        return RequestSpec("GET", f"{self._JOBS_PATH}/failures/new", params=params)

    def _timeseries_spec(
        self, collection_id: str | None = None, window_hours: int | None = None
    ) -> RequestSpec:
        """A GET of the lightweight hourly job trends (done/failed/arrivals/backlog sparklines)."""
        params: dict[str, object] = {}
        if collection_id is not None:
            params["collection_id"] = collection_id
        if window_hours is not None:
            params["window_hours"] = window_hours
        return RequestSpec("GET", f"{self._JOBS_PATH}/timeseries", params=params or None)

    def _get_spec(self, job_id: str) -> RequestSpec:
        """
        Build the spec for fetching one job's status.

        Args:
            job_id (str): The job's UUID.

        Returns:
            RequestSpec: A GET on the job resource.
        """
        return RequestSpec("GET", f"{self._JOBS_PATH}/{job_id}")

    def _get_events_spec(self, job_id: str) -> RequestSpec:
        """
        Build the spec for fetching a job's per-node execution trace.

        Args:
            job_id (str): The job's UUID.

        Returns:
            RequestSpec: A GET on the job's ``/events`` sub-resource.
        """
        return RequestSpec("GET", f"{self._JOBS_PATH}/{job_id}/events")

    def _get_event_payload_spec(self, job_id: str, event_id: str, slot: str) -> RequestSpec:
        """
        Build the spec for fetching one stage-event's full raw input/output payload.

        Args:
            job_id (str): The job's UUID.
            event_id (str): The stage-event row's UUID (JobEvent.event_id).
            slot (str): Which side to fetch — "input" or "output".

        Returns:
            RequestSpec: A GET on the event's ``/payload`` sub-resource, scoped by slot.
        """
        return RequestSpec(
            "GET",
            f"{self._JOBS_PATH}/{job_id}/events/{event_id}/payload",
            params={"slot": slot},
        )

    def _live_workers_spec(self) -> RequestSpec:
        """
        Build the spec for the live worker-activity view.

        Returns:
            RequestSpec: A GET on the jobs ``/workers/live`` route.
        """
        return RequestSpec("GET", f"{self._JOBS_PATH}/workers/live")

    def _cancel_spec(self, job_id: str, force: bool) -> RequestSpec:
        """
        Build the spec for cancelling a job.

        Args:
            job_id (str): The job's UUID.
            force (bool): Immediately terminate a running/wedged job instead of asking it to stop
                cooperatively at its next stage boundary.

        Returns:
            RequestSpec: A POST on the job's ``/cancel`` route carrying ``force`` as a query param.
        """
        return RequestSpec("POST", f"{self._JOBS_PATH}/{job_id}/cancel", params={"force": force})

    def _cost_spec(self, collection_id: str) -> RequestSpec:
        """A GET of a collection's paid text-gen roll-up (tokens + USD)."""
        return RequestSpec(
            "GET", f"{self._JOBS_PATH}/cost", params={"collection_id": collection_id}
        )

    def _queue_spec(self, collection_id: str | None) -> RequestSpec:
        """A GET of backlog counters (pending/running) — fleet-wide (root) or per-collection."""
        params = {"collection_id": collection_id} if collection_id is not None else None
        return RequestSpec("GET", f"{self._JOBS_PATH}/queue", params=params)

    def _stage_durations_spec(self, collection_id: str) -> RequestSpec:
        """A GET of a collection's average per-stage wall-clock (the ETA basis)."""
        return RequestSpec(
            "GET", f"{self._JOBS_PATH}/stage-durations", params={"collection_id": collection_id}
        )


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


class SyncJobs(SyncResource, _JobsSpecs):
    """Synchronous ingestion-job monitoring."""

    def list(
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
        return self._transport.request(
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

    def failure_breakdown(
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
        return self._transport.request(
            self._failure_breakdown_spec(collection_id, window_hours), FailureBreakdown
        )

    def new_failures(
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
        return self._transport.request(
            self._new_failures_spec(since, collection_id, include_ids, limit), NewFailures
        )

    def timeseries(
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
        return self._transport.request(
            self._timeseries_spec(collection_id, window_hours), JobTimeseries
        )

    def get(self, job_id: str) -> JobStatus:
        """
        Fetch one job's live status.

        Args:
            job_id (str): The job's UUID.

        Returns:
            JobStatus: The job's current state.
        """
        return self._transport.request(self._get_spec(job_id), JobStatus)

    def get_events(self, job_id: str) -> JobTrace:
        """
        Fetch a job's per-node execution trace, in run order.

        Args:
            job_id (str): The job's UUID.

        Returns:
            JobTrace: The ordered per-node trace.
        """
        return self._transport.request(self._get_events_spec(job_id), JobTrace)

    def get_event_payload(
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
        return self._transport.request(
            self._get_event_payload_spec(job_id, event_id, slot), JobEventPayload
        )

    def live_workers(self) -> WorkersLive:
        """
        Fetch everything running right now, grouped by worker.

        Returns:
            WorkersLive: The live per-worker activity view.
        """
        return self._transport.request(self._live_workers_spec(), WorkersLive)

    def cancel(self, job_id: str, force: bool = False) -> CancelResult:
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
        return self._transport.request(self._cancel_spec(job_id, force), CancelResult)

    def cost(self, collection_id: str) -> CollectionCost:
        """The collection's paid text-gen roll-up — tokens + USD summed over its documents' jobs."""
        return self._transport.request(self._cost_spec(collection_id), CollectionCost)

    def queue(self, collection_id: str | None = None) -> QueueDepth:
        """Backlog counters (pending/running) — fleet-wide (root) or for one collection."""
        return self._transport.request(self._queue_spec(collection_id), QueueDepth)

    def stage_durations(self, collection_id: str) -> StageDurations:
        """Average per-stage wall-clock over the collection's done jobs (a running job's ETA basis)."""
        return self._transport.request(self._stage_durations_spec(collection_id), StageDurations)


__all__ = ["AsyncJobs", "SyncJobs"]
