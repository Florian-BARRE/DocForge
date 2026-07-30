# ====== Code Summary ======
# The jobs resource — the live ingestion status the UI polls. All URL/param logic lives once in the
# pure _JobsSpecs mixin so AsyncJobs and SyncJobs differ ONLY by ``await``. The collection filter on
# the list endpoint is a query parameter (not a path segment), threaded through the spec's params.

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.jobs import JobStatus, JobTrace, WorkersLive
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _JobsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the jobs endpoints — the single source of URL/param logic."""

    _JOBS_PATH = "/jobs"

    def _list_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for listing a collection's jobs.

        Args:
            collection_id (str): The collection whose jobs to list (a QUERY parameter).

        Returns:
            RequestSpec: A GET on the jobs collection filtered by ``collection_id``.
        """
        return RequestSpec("GET", self._JOBS_PATH, params={"collection_id": collection_id})

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


class AsyncJobs(AsyncResource, _JobsSpecs):
    """Asynchronous ingestion-job monitoring."""

    async def list(self, collection_id: str) -> list[JobStatus]:
        """
        List a collection's jobs, newest first.

        Args:
            collection_id (str): The collection whose jobs to list.

        Returns:
            list[JobStatus]: Every job of the collection with its live state.
        """
        return await self._transport.request(self._list_spec(collection_id), list[JobStatus])

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


class SyncJobs(SyncResource, _JobsSpecs):
    """Synchronous ingestion-job monitoring."""

    def list(self, collection_id: str) -> list[JobStatus]:
        """
        List a collection's jobs, newest first.

        Args:
            collection_id (str): The collection whose jobs to list.

        Returns:
            list[JobStatus]: Every job of the collection with its live state.
        """
        return self._transport.request(self._list_spec(collection_id), list[JobStatus])

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


__all__ = ["AsyncJobs", "SyncJobs"]
