# ====== Code Summary ======
# The pure ``RequestSpec`` builders of the jobs (the live ingestion status the UI polls) resource —
# the single source of its URL/param/body logic, shared verbatim by the async and sync resources so
# their bodies differ ONLY by ``await``.

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from .._base import _ResourceMixin


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
