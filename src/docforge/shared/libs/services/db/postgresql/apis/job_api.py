# ====== Code Summary ======
# JobApi — the public data-access facade for ingestion observability (the job record and its per-
# stage event timeline). The implementation is split by responsibility into ``apis/jobs/``; this
# class only re-exposes every public method under its historical name, so callers (the facades, the
# tests) keep importing ``JobApi`` from here and monkeypatching its attributes unchanged.
#
#   JobLifecycleApi        create / claim / progress / done / failed / cancel / force-terminal
#   JobLookupApi           single-job and per-document / per-collection lookups
#   JobStageEventApi       the stage-event timeline and the persisted execution tree
#   WorkerHeartbeatApi     worker liveness rows and the restart reclaim read
#   JobUsageApi            token / cost metering and per-stage duration averages
#   JobTraceRetentionApi   trace-payload purge id sets, ref clearing and the history prune
#   JobReaperApi           the stale / over-timeout candidate reads
#   JobListingApi          jobs joined to display names, the triage list and its count
#   JobDashboardApi        backlog, status histogram, failure breakdown, trend counts

# ====== Internal Project Imports ======
from .jobs import (
    FailureAggregates,
    JobDashboardApi,
    JobLifecycleApi,
    JobListingApi,
    JobLookupApi,
    JobReaperApi,
    JobStageEventApi,
    JobTraceRetentionApi,
    JobUsageApi,
    JobWithNames,
    TimeseriesAggregates,
    WorkerHeartbeatApi,
)


class JobApi:
    """Static facade over the job data-access APIs of ``apis/jobs/`` (one name per method)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobApi is a static-only class and cannot be instantiated.")

    # ---- JobLifecycleApi
    create = staticmethod(JobLifecycleApi.create)
    mark_running = staticmethod(JobLifecycleApi.mark_running)
    set_progress = staticmethod(JobLifecycleApi.set_progress)
    set_items = staticmethod(JobLifecycleApi.set_items)
    mark_done = staticmethod(JobLifecycleApi.mark_done)
    mark_failed = staticmethod(JobLifecycleApi.mark_failed)
    request_cancel = staticmethod(JobLifecycleApi.request_cancel)
    is_cancel_requested = staticmethod(JobLifecycleApi.is_cancel_requested)
    mark_terminal = staticmethod(JobLifecycleApi.mark_terminal)
    # ---- JobLookupApi
    get = staticmethod(JobLookupApi.get)
    get_latest_for_document = staticmethod(JobLookupApi.get_latest_for_document)
    get_latest_successful_for_document = staticmethod(
        JobLookupApi.get_latest_successful_for_document
    )
    get_active_for_document = staticmethod(JobLookupApi.get_active_for_document)
    list_for_collection = staticmethod(JobLookupApi.list_for_collection)
    count_for_collection = staticmethod(JobLookupApi.count_for_collection)
    list_active = staticmethod(JobLookupApi.list_active)
    list_active_for_collection = staticmethod(JobLookupApi.list_active_for_collection)
    # ---- JobStageEventApi
    record_event = staticmethod(JobStageEventApi.record_event)
    finalize_event = staticmethod(JobStageEventApi.finalize_event)
    persist_execution_tree = staticmethod(JobStageEventApi.persist_execution_tree)
    _trace_sort_key = staticmethod(JobStageEventApi._trace_sort_key)
    events_query = staticmethod(JobStageEventApi.events_query)
    list_events = staticmethod(JobStageEventApi.list_events)
    get_event = staticmethod(JobStageEventApi.get_event)
    # ---- WorkerHeartbeatApi
    upsert_heartbeat = staticmethod(WorkerHeartbeatApi.upsert_heartbeat)
    delete_heartbeat = staticmethod(WorkerHeartbeatApi.delete_heartbeat)
    prune_stale_heartbeats = staticmethod(WorkerHeartbeatApi.prune_stale_heartbeats)
    list_heartbeats = staticmethod(WorkerHeartbeatApi.list_heartbeats)
    list_running_for_worker = staticmethod(WorkerHeartbeatApi.list_running_for_worker)
    # ---- JobUsageApi
    add_usage = staticmethod(JobUsageApi.add_usage)
    avg_stage_durations = staticmethod(JobUsageApi.avg_stage_durations)
    collection_cost = staticmethod(JobUsageApi.collection_cost)
    # ---- JobTraceRetentionApi
    list_trace_job_ids_before = staticmethod(JobTraceRetentionApi.list_trace_job_ids_before)
    list_job_ids_for_document = staticmethod(JobTraceRetentionApi.list_job_ids_for_document)
    list_job_ids_for_documents = staticmethod(JobTraceRetentionApi.list_job_ids_for_documents)
    list_job_ids_for_collection = staticmethod(JobTraceRetentionApi.list_job_ids_for_collection)
    list_terminal_job_ids_for_collection = staticmethod(
        JobTraceRetentionApi.list_terminal_job_ids_for_collection
    )
    list_terminal_job_ids_for_document = staticmethod(
        JobTraceRetentionApi.list_terminal_job_ids_for_document
    )
    clear_trace_refs = staticmethod(JobTraceRetentionApi.clear_trace_refs)
    set_trace_payload_bytes = staticmethod(JobTraceRetentionApi.set_trace_payload_bytes)
    prune_history = staticmethod(JobTraceRetentionApi.prune_history)
    # ---- JobReaperApi
    list_stale = staticmethod(JobReaperApi.list_stale)
    list_over_job_timeout = staticmethod(JobReaperApi.list_over_job_timeout)
    # ---- JobListingApi
    _with_names_select = staticmethod(JobListingApi._with_names_select)
    _row_to_names = staticmethod(JobListingApi._row_to_names)
    get_with_names = staticmethod(JobListingApi.get_with_names)
    list_for_collection_with_names = staticmethod(JobListingApi.list_for_collection_with_names)
    list_active_with_names = staticmethod(JobListingApi.list_active_with_names)
    list_with_names = staticmethod(JobListingApi.list_with_names)
    count_jobs = staticmethod(JobListingApi.count_jobs)
    # ---- JobDashboardApi
    queue_depth = staticmethod(JobDashboardApi.queue_depth)
    status_counts = staticmethod(JobDashboardApi.status_counts)
    last_successful_ingest_at = staticmethod(JobDashboardApi.last_successful_ingest_at)
    last_successful_ingest_at_by_collections = staticmethod(
        JobDashboardApi.last_successful_ingest_at_by_collections
    )
    failure_breakdown = staticmethod(JobDashboardApi.failure_breakdown)
    count_failed_since = staticmethod(JobDashboardApi.count_failed_since)
    list_failed_since = staticmethod(JobDashboardApi.list_failed_since)
    job_timeseries = staticmethod(JobDashboardApi.job_timeseries)


__all__ = ["JobApi", "JobWithNames", "FailureAggregates", "TimeseriesAggregates"]
