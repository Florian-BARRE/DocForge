# ====== Code Summary ======
# The jobs resource — the live ingestion status the UI polls. All URL/param logic lives once in the
# pure _JobsSpecs mixin so AsyncJobs and SyncJobs differ ONLY by ``await``. The collection filter on
# the list endpoint is a query parameter (not a path segment), threaded through the spec's params.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.jobs import CancelResult, JobPage, JobStatus, JobTrace, WorkersLive
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _JobsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the jobs endpoints — the single source of URL/param logic."""

    _JOBS_PATH = "/jobs"

    def _list_spec(
        self, collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> RequestSpec:
        """
        Build the spec for listing a collection's jobs (a bounded, paginated page).

        Args:
            collection_id (str): The collection whose jobs to list (a QUERY parameter).
            limit (int | None): Page size; the server clamps it to its ceiling. Omitted → the
                server default (its ceiling).
            offset (int | None): Rows to skip for paging. Omitted → 0.

        Returns:
            RequestSpec: A GET on the jobs collection filtered by ``collection_id`` (+ paging).
        """
        params: dict[str, object] = {"collection_id": collection_id}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return RequestSpec("GET", self._JOBS_PATH, params=params)

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


class AsyncJobs(AsyncResource, _JobsSpecs):
    """Asynchronous ingestion-job monitoring."""

    async def list(
        self, collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> JobPage:
        """
        List one bounded page of a collection's jobs, newest first.

        Args:
            collection_id (str): The collection whose jobs to list.
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            offset (int | None): Rows to skip for paging (default 0).

        Returns:
            JobPage: The page (``.jobs``) plus ``total``/``limit``/``offset`` for pagination.
        """
        return await self._transport.request(self._list_spec(collection_id, limit, offset), JobPage)

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


class SyncJobs(SyncResource, _JobsSpecs):
    """Synchronous ingestion-job monitoring."""

    def list(
        self, collection_id: str, limit: int | None = None, offset: int | None = None
    ) -> JobPage:
        """
        List one bounded page of a collection's jobs, newest first.

        Args:
            collection_id (str): The collection whose jobs to list.
            limit (int | None): Page size; the server clamps it to its ceiling (default = ceiling).
            offset (int | None): Rows to skip for paging (default 0).

        Returns:
            JobPage: The page (``.jobs``) plus ``total``/``limit``/``offset`` for pagination.
        """
        return self._transport.request(self._list_spec(collection_id, limit, offset), JobPage)

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


__all__ = ["AsyncJobs", "SyncJobs"]
