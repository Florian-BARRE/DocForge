# ====== Code Summary ======
# Characterization of the statements JobApi sends to the database TODAY (safety net for the
# data-layer refactoring campaign). No database: each public method runs against a RecordingSession
# with fixed arguments and the operations it records (compiled PostgreSQL statements, ORM get / add,
# attribute writes) are compared with the inline golden. The set of public method names is frozen
# too, so a split of JobApi cannot silently drop or rename one. Methods covered "name only" are
# listed in ``NAME_ONLY``.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis.job_api import JobApi

# ====== Local Project Imports ======
from .support.api_runner import ApiRunner, CallSpec
from .support.job_api_golden import JOB_API_GOLDEN
from .support.job_call_specs import JOB_SPECS, NAME_ONLY

#: The public surface of JobApi, frozen. Adding a method means adding it here AND a call spec.
FROZEN_PUBLIC_METHODS: frozenset[str] = frozenset(
    {
        "add_usage",
        "avg_stage_durations",
        "clear_trace_refs",
        "collection_cost",
        "count_failed_since",
        "count_for_collection",
        "count_jobs",
        "create",
        "delete_heartbeat",
        "events_query",
        "failure_breakdown",
        "finalize_event",
        "get",
        "get_active_for_document",
        "get_event",
        "get_latest_for_document",
        "get_latest_successful_for_document",
        "get_with_names",
        "is_cancel_requested",
        "job_timeseries",
        "last_successful_ingest_at",
        "last_successful_ingest_at_by_collections",
        "list_active",
        "list_active_for_collection",
        "list_active_with_names",
        "list_events",
        "list_failed_since",
        "list_for_collection",
        "list_for_collection_with_names",
        "list_heartbeats",
        "list_job_ids_for_collection",
        "list_job_ids_for_document",
        "list_job_ids_for_documents",
        "list_over_job_timeout",
        "list_running_for_worker",
        "list_stale",
        "list_terminal_job_ids_for_collection",
        "list_terminal_job_ids_for_document",
        "list_trace_job_ids_before",
        "list_with_names",
        "mark_done",
        "mark_failed",
        "mark_running",
        "mark_terminal",
        "persist_execution_tree",
        "prune_history",
        "prune_stale_heartbeats",
        "queue_depth",
        "record_event",
        "request_cancel",
        "set_items",
        "set_progress",
        "set_trace_payload_bytes",
        "status_counts",
        "upsert_heartbeat",
    }
)


def test_public_method_set_is_frozen() -> None:
    """JobApi exposes exactly the frozen public methods — nothing dropped, renamed or added."""
    assert set(ApiRunner.public_methods(JobApi)) == FROZEN_PUBLIC_METHODS


def test_every_public_method_has_a_call_spec_or_is_name_only() -> None:
    """Each public method is either exercised by a call spec or explicitly listed as name-only."""
    exercised = {spec.method for spec in JOB_SPECS}
    assert exercised | NAME_ONLY == FROZEN_PUBLIC_METHODS
    assert exercised.isdisjoint(NAME_ONLY)


def test_golden_and_call_specs_list_the_same_calls() -> None:
    """No golden entry is stale and no call spec lacks its golden."""
    assert set(JOB_API_GOLDEN) == {spec.key for spec in JOB_SPECS}


@pytest.mark.parametrize("spec", JOB_SPECS, ids=lambda spec: spec.key)
async def test_statements_match_the_golden(spec: CallSpec) -> None:
    """The operations a JobApi call records are exactly the golden ones."""
    assert await ApiRunner.trace(spec) == JOB_API_GOLDEN[spec.key]
