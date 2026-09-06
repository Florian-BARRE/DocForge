# ====== Code Summary ======
# The jobs resource — the live ingestion status the UI polls. All URL/param logic lives once in the
# pure _JobsSpecs mixin so AsyncJobs and SyncJobs differ ONLY by ``await``. The collection filter on
# the list endpoint is a query parameter (not a path segment), threaded through the spec's params.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.jobs import (
    CancelResult,
    CollectionCost,
    JobPage,
    JobStatus,
    JobTrace,
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
    ) -> RequestSpec:
        """
        Build the spec for listing jobs (a bounded, paginated page) — scoped or fleet-wide.

        Args:
            collection_id (str | None): Scope to one collection (a QUERY parameter). Omitted → a
                FLEET-WIDE listing (full-access keys only) — the "All Jobs" view.
            status (list[str] | None): Filter to these job statuses (pending/running/done/failed/
                cancelled), passed as a repeated query param. Omitted → all statuses.
            order (str | None): ``newest`` (created_at DESC, the default) or ``oldest`` (created_at
                ASC — FIFO/"what runs next"). Omitted → the server default (newest).
            limit (int | None): Page size; the server clamps it to its ceiling. Omitted → the
                server default (its ceiling).
            offset (int | None): Rows to skip for paging. Omitted → 0.

        Returns:
            RequestSpec: A GET on the jobs collection with the optional scope/status/order/paging.
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
        return RequestSpec("GET", self._JOBS_PATH, params=params or None)

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
    ) -> JobPage:
        """
        List one bounded page of jobs — a collection's, or (with no ``collection_id``) the fleet's.

        Args:
            collection_id (str | None): Scope to one collection. Omitted → a FLEET-WIDE listing
                (full-access keys only) — the "All Jobs" view.
            status (list[str] | None): Filter to these statuses (pending/running/done/failed/
                cancelled). Omitted → all statuses.
            order (str | None): ``newest`` (default, created_at DESC) or ``oldest`` (created_at ASC —
                FIFO/"what runs next", typically with ``status=['pending']``).
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            offset (int | None): Rows to skip for paging (default 0).

        Returns:
            JobPage: The page (``.jobs``) plus ``total``/``limit``/``offset`` for pagination.
        """
        return await self._transport.request(
            self._list_spec(collection_id, status, order, limit, offset), JobPage
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
    ) -> JobPage:
        """
        List one bounded page of jobs — a collection's, or (with no ``collection_id``) the fleet's.

        Args:
            collection_id (str | None): Scope to one collection. Omitted → a FLEET-WIDE listing
                (full-access keys only) — the "All Jobs" view.
            status (list[str] | None): Filter to these statuses (pending/running/done/failed/
                cancelled). Omitted → all statuses.
            order (str | None): ``newest`` (default, created_at DESC) or ``oldest`` (created_at ASC —
                FIFO/"what runs next", typically with ``status=['pending']``).
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            offset (int | None): Rows to skip for paging (default 0).

        Returns:
            JobPage: The page (``.jobs``) plus ``total``/``limit``/``offset`` for pagination.
        """
        return self._transport.request(
            self._list_spec(collection_id, status, order, limit, offset), JobPage
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
