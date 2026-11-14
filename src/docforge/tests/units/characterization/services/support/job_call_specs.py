# ====== Code Summary ======
# The fixed-argument call table for every public JobApi method. One spec per method (plus a few
# variants where a branch changes the SQL), each built from constants only so the compiled
# statements are deterministic. ``NAME_ONLY`` lists the methods this characterization covers by name
# alone (see its comment).

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from decimal import Decimal

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis.job_api import JobApi
from shared_libs.services.db.postgresql.tables import Job, JobStageEvent, JobStatus

# ====== Local Project Imports ======
from .api_runner import CallSpec

JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
EVENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DOC_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
DOC_ID_2 = uuid.UUID("33333333-3333-3333-3333-333333333334")
COLLECTION_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
COLLECTION_ID_2 = uuid.UUID("44444444-4444-4444-4444-444444444445")
WHEN = datetime(2026, 1, 2, 3, 4, 5)
EARLIER = datetime(2026, 1, 1, 0, 0, 0)

#: Public methods characterized by NAME ONLY: ``persist_execution_tree`` needs a whole
#: NodeExecutionRecord tree and flattens it before touching the session, so its statements depend on
#: the record's shape rather than on the method's own SQL.
NAME_ONLY: frozenset[str] = frozenset({"persist_execution_tree"})

_ALL_FILTERS = dict(
    stage="parse",
    error_type="TimeoutError",
    search="report",
    created_after=EARLIER,
    created_before=WHEN,
)

JOB_SPECS: tuple[CallSpec, ...] = (
    CallSpec("add_usage", "", lambda s: JobApi.add_usage(s, JOB_ID, 10, 20, 0.5)),
    CallSpec("add_usage", "no-cost", lambda s: JobApi.add_usage(s, JOB_ID, 10, 20, None)),
    CallSpec("avg_stage_durations", "", lambda s: JobApi.avg_stage_durations(s, COLLECTION_ID)),
    CallSpec("clear_trace_refs", "", lambda s: JobApi.clear_trace_refs(s, [JOB_ID])),
    CallSpec("clear_trace_refs", "empty", lambda s: JobApi.clear_trace_refs(s, [])),
    CallSpec("collection_cost", "", lambda s: JobApi.collection_cost(s, COLLECTION_ID)),
    CallSpec("count_failed_since", "", lambda s: JobApi.count_failed_since(s, EARLIER)),
    CallSpec(
        "count_failed_since",
        "collection",
        lambda s: JobApi.count_failed_since(s, EARLIER, COLLECTION_ID),
    ),
    CallSpec("count_for_collection", "", lambda s: JobApi.count_for_collection(s, COLLECTION_ID)),
    CallSpec("count_jobs", "", lambda s: JobApi.count_jobs(s)),
    CallSpec(
        "count_jobs",
        "all-filters",
        lambda s: JobApi.count_jobs(
            s, COLLECTION_ID, [JobStatus.FAILED, JobStatus.DONE], **_ALL_FILTERS
        ),
    ),
    CallSpec("create", "", lambda s: JobApi.create(s, Job())),
    CallSpec("delete_heartbeat", "", lambda s: JobApi.delete_heartbeat(s, "worker-1")),
    CallSpec("events_query", "", lambda s: JobApi.events_query(JOB_ID)),
    CallSpec("events_query", "lean-after", lambda s: JobApi.events_query(JOB_ID, False, WHEN)),
    CallSpec("failure_breakdown", "", lambda s: JobApi.failure_breakdown(s, EARLIER)),
    CallSpec(
        "failure_breakdown",
        "collection-top3",
        lambda s: JobApi.failure_breakdown(s, EARLIER, COLLECTION_ID, 3),
    ),
    CallSpec(
        "finalize_event",
        "",
        lambda s: JobApi.finalize_event(s, EVENT_ID, "done", WHEN, "ok", 1, 2, Decimal("0.5")),
    ),
    CallSpec("get", "", lambda s: JobApi.get(s, JOB_ID)),
    CallSpec("get_active_for_document", "", lambda s: JobApi.get_active_for_document(s, DOC_ID)),
    CallSpec("get_event", "", lambda s: JobApi.get_event(s, JOB_ID, EVENT_ID)),
    CallSpec("get_latest_for_document", "", lambda s: JobApi.get_latest_for_document(s, DOC_ID)),
    CallSpec(
        "get_latest_successful_for_document",
        "",
        lambda s: JobApi.get_latest_successful_for_document(s, DOC_ID),
    ),
    CallSpec("get_with_names", "", lambda s: JobApi.get_with_names(s, JOB_ID)),
    CallSpec("is_cancel_requested", "", lambda s: JobApi.is_cancel_requested(s, JOB_ID)),
    CallSpec("job_timeseries", "", lambda s: JobApi.job_timeseries(s, EARLIER)),
    CallSpec(
        "job_timeseries",
        "collection",
        lambda s: JobApi.job_timeseries(s, EARLIER, COLLECTION_ID),
    ),
    CallSpec(
        "last_successful_ingest_at",
        "",
        lambda s: JobApi.last_successful_ingest_at(s, COLLECTION_ID),
    ),
    CallSpec(
        "last_successful_ingest_at_by_collections",
        "",
        lambda s: JobApi.last_successful_ingest_at_by_collections(
            s, [COLLECTION_ID, COLLECTION_ID_2]
        ),
    ),
    CallSpec("list_active", "", lambda s: JobApi.list_active(s)),
    CallSpec(
        "list_active_for_collection",
        "",
        lambda s: JobApi.list_active_for_collection(s, COLLECTION_ID),
    ),
    CallSpec("list_active_with_names", "", lambda s: JobApi.list_active_with_names(s)),
    CallSpec("list_events", "", lambda s: JobApi.list_events(s, JOB_ID)),
    CallSpec("list_events", "lean-after", lambda s: JobApi.list_events(s, JOB_ID, False, WHEN)),
    CallSpec("list_failed_since", "", lambda s: JobApi.list_failed_since(s, EARLIER)),
    CallSpec(
        "list_failed_since",
        "collection-limit",
        lambda s: JobApi.list_failed_since(s, EARLIER, COLLECTION_ID, 7),
    ),
    CallSpec("list_for_collection", "", lambda s: JobApi.list_for_collection(s, COLLECTION_ID)),
    CallSpec(
        "list_for_collection_with_names",
        "",
        lambda s: JobApi.list_for_collection_with_names(s, COLLECTION_ID),
    ),
    CallSpec(
        "list_for_collection_with_names",
        "page",
        lambda s: JobApi.list_for_collection_with_names(s, COLLECTION_ID, 10, 20),
    ),
    CallSpec("list_heartbeats", "", lambda s: JobApi.list_heartbeats(s)),
    CallSpec(
        "list_job_ids_for_collection",
        "",
        lambda s: JobApi.list_job_ids_for_collection(s, COLLECTION_ID),
    ),
    CallSpec(
        "list_job_ids_for_document", "", lambda s: JobApi.list_job_ids_for_document(s, DOC_ID)
    ),
    CallSpec(
        "list_job_ids_for_documents",
        "",
        lambda s: JobApi.list_job_ids_for_documents(s, [DOC_ID, DOC_ID_2]),
    ),
    CallSpec(
        "list_over_job_timeout",
        "",
        lambda s: JobApi.list_over_job_timeout(s, 3600.0, 60.0, 180.0),
    ),
    CallSpec(
        "list_over_job_timeout",
        "rebuild-timeout",
        lambda s: JobApi.list_over_job_timeout(s, 3600.0, 60.0, 180.0, 7200.0),
    ),
    CallSpec(
        "list_running_for_worker", "", lambda s: JobApi.list_running_for_worker(s, "worker-1")
    ),
    CallSpec("list_stale", "", lambda s: JobApi.list_stale(s, 1200.0, 180.0)),
    CallSpec(
        "list_terminal_job_ids_for_collection",
        "",
        lambda s: JobApi.list_terminal_job_ids_for_collection(s, COLLECTION_ID),
    ),
    CallSpec(
        "list_terminal_job_ids_for_document",
        "",
        lambda s: JobApi.list_terminal_job_ids_for_document(s, DOC_ID),
    ),
    CallSpec(
        "list_trace_job_ids_before", "", lambda s: JobApi.list_trace_job_ids_before(s, WHEN, 100)
    ),
    CallSpec("list_with_names", "", lambda s: JobApi.list_with_names(s)),
    CallSpec(
        "list_with_names",
        "all-filters-page",
        lambda s: JobApi.list_with_names(
            s, COLLECTION_ID, [JobStatus.RUNNING], 25, 50, True, sort_by="status", **_ALL_FILTERS
        ),
    ),
    CallSpec(
        "list_with_names",
        "oldest-first",
        lambda s: JobApi.list_with_names(s, COLLECTION_ID, newest_first=False),
    ),
    CallSpec("mark_done", "", lambda s: JobApi.mark_done(s, JOB_ID, WHEN)),
    CallSpec("mark_failed", "", lambda s: JobApi.mark_failed(s, JOB_ID, "boom", WHEN)),
    CallSpec(
        "mark_failed",
        "attributed",
        lambda s: JobApi.mark_failed(s, JOB_ID, "boom", WHEN, "node-1", "ocr", 3, "TimeoutError"),
    ),
    CallSpec(
        "mark_running",
        "",
        lambda s: JobApi.mark_running(s, JOB_ID, "worker-1", 2, WHEN),
        {"status": JobStatus.PENDING},
    ),
    CallSpec(
        "mark_running",
        "terminal-job-untouched",
        lambda s: JobApi.mark_running(s, JOB_ID, "worker-1", 2, WHEN),
        {"status": JobStatus.DONE},
    ),
    CallSpec(
        "mark_terminal",
        "",
        lambda s: JobApi.mark_terminal(s, JOB_ID, JobStatus.CANCELLED, "stopped", WHEN),
    ),
    CallSpec(
        "mark_terminal",
        "attributed",
        lambda s: JobApi.mark_terminal(
            s, JOB_ID, JobStatus.FAILED, "reaped", WHEN, "worker_killed"
        ),
    ),
    CallSpec("prune_history", "", lambda s: JobApi.prune_history(s, WHEN)),
    CallSpec("prune_stale_heartbeats", "", lambda s: JobApi.prune_stale_heartbeats(s, 300.0)),
    CallSpec("queue_depth", "", lambda s: JobApi.queue_depth(s)),
    CallSpec("queue_depth", "collection", lambda s: JobApi.queue_depth(s, COLLECTION_ID)),
    CallSpec("record_event", "", lambda s: JobApi.record_event(s, JobStageEvent())),
    CallSpec("request_cancel", "", lambda s: JobApi.request_cancel(s, JOB_ID)),
    CallSpec("set_items", "", lambda s: JobApi.set_items(s, JOB_ID, 3, 10)),
    CallSpec("set_items", "unknown-total", lambda s: JobApi.set_items(s, JOB_ID, 3, None)),
    CallSpec("set_progress", "", lambda s: JobApi.set_progress(s, JOB_ID, "parse", 40)),
    CallSpec(
        "set_trace_payload_bytes", "", lambda s: JobApi.set_trace_payload_bytes(s, JOB_ID, 2048)
    ),
    CallSpec("status_counts", "", lambda s: JobApi.status_counts(s)),
    CallSpec(
        "upsert_heartbeat",
        "",
        lambda s: JobApi.upsert_heartbeat(s, "worker-1", "worker", WHEN, EARLIER),
    ),
    CallSpec(
        "upsert_heartbeat",
        "with-metrics",
        lambda s: JobApi.upsert_heartbeat(
            s, "worker-1", "worker", WHEN, EARLIER, 4, 12.5, 512.0, 33.3
        ),
    ),
)
