# ====== Code Summary ======
# CHARACTERIZATION (safety net for the refactoring campaign) of ``ingest_document``'s side-effect
# ORDER. Each test drives one path of the arq task through recording fakes (see
# characterization_ingest_harness.py) and asserts the exact ordered list of facade / store calls and the
# job + document status transitions as a GOLDEN. They record what the code does TODAY: when a golden
# changes, the refactor changed the behaviour — decide on purpose, never "fix the test". No database,
# Redis or S3 is involved. Protects the planned extraction of the IngestJob.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
import pytest
from characterization_ingest_harness import IngestHarness, replay_job
from runner import PipelineRunError
from runner.breadcrumb import FailureBreadcrumb

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import ProgressEvent, ProgressPhase
from shared_libs.services.db.postgresql.tables import JobStatus

# The rehydrate prefix every run that gets past the dequeue guard shares.
_CLAIM = ["jobs.get", "jobs.mark_running", "ingestion.mark_processing"]
_REHYDRATE_FULL = [
    "documents.get",
    "collections.get",
    "collections.get_schema",
    "s3.get",
    "documents.get_metadata",
]

_SUCCESS_GOLDEN = [
    *_CLAIM,
    *_REHYDRATE_FULL,
    "StageCacheHook",
    "runner.run",
    "jobs.persist_execution_tree",
    "RunTranslator.translate",
    "ingestion.store_blobs",
    "ingestion.save",
    "ingestion.index",
    "filters.sync_document_filter_payloads",
    "meta_vectors.sync_document_meta_vectors",
    "jobs.mark_done",
]


@pytest.fixture
def make_harness(monkeypatch, jobs_core, jobs_replay, jobs_cancellation):
    """Factory of a wired IngestHarness (every patch is undone by monkeypatch at teardown)."""

    def _make(**options) -> IngestHarness:
        return IngestHarness(monkeypatch, jobs_core, jobs_replay, jobs_cancellation, **options)

    return _make


# ------------------------------------------------------------------ success paths
async def test_success_call_order_is_claim_rehydrate_run_persist_index_done(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    assert harness.calls == _SUCCESS_GOLDEN


async def test_success_status_transitions_are_running_processing_saved_done(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    assert harness.transitions == [
        "job: RUNNING",
        "document: PROCESSING",
        "document: DONE (or DONE with a 0-chunk warning)",
        "job: DONE",
    ]


async def test_success_claims_the_job_with_the_worker_id_and_first_attempt(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    claim = harness.kwargs_of("jobs.mark_running")
    assert (claim["worker_id"], claim["attempt"]) == ("w1", 1)
    assert harness.args_of("jobs.mark_running") == (harness.job_id,)


async def test_success_saves_without_a_warning_and_marks_done(make_harness) -> None:
    harness = make_harness(chunks=2)

    await harness.run_ingest()

    assert harness.kwargs_of("ingestion.save")["warning_reason"] is None
    assert "jobs.mark_failed" not in harness.calls


async def test_success_with_zero_chunks_saves_a_warning_and_skips_the_index(make_harness) -> None:
    """0 chunks → 0 points: DONE-with-warning, the Qdrant index and both denormalisations are skipped."""
    harness = make_harness(chunks=0, points=0)

    await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_FULL,
        "StageCacheHook",
        "runner.run",
        "jobs.persist_execution_tree",
        "RunTranslator.translate",
        "ingestion.store_blobs",
        "ingestion.save",
        "jobs.mark_done",
    ]
    assert "0 chunks" in harness.kwargs_of("ingestion.save")["warning_reason"]


async def test_full_trace_level_stores_payloads_before_persisting_the_tree(make_harness) -> None:
    harness = make_harness(trace_verbosity="full", trace_ceiling="full")

    await harness.run_ingest()

    stored = harness.calls.index("ingestion.store_trace_payloads")
    persisted = harness.calls.index("jobs.persist_execution_tree")
    assert stored == persisted - 1
    assert harness.calls.index("runner.run") == stored - 1
    assert harness.kwargs_of("jobs.persist_execution_tree")["refs"] == {"ref": "x"}


async def test_shape_trace_level_never_stores_trace_payloads(make_harness) -> None:
    harness = make_harness(trace_verbosity="full", trace_ceiling="shape")

    await harness.run_ingest()

    assert "ingestion.store_trace_payloads" not in harness.calls
    assert harness.kwargs_of("jobs.persist_execution_tree")["refs"] is None


# ------------------------------------------------------------------ the stage-cache hook
async def test_force_builds_no_cache_hook_and_runs_with_cache_hook_none(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest(force=True)

    assert harness.calls == [name for name in _SUCCESS_GOLDEN if name != "StageCacheHook"]
    assert harness.kwargs_of("runner.run")["cache_hook"] is None


async def test_a_normal_run_hands_the_built_cache_hook_to_the_runner(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    assert harness.kwargs_of("runner.run")["cache_hook"] is harness.cache_hook


async def test_cache_disabled_in_config_builds_no_cache_hook(make_harness) -> None:
    harness = make_harness(cache_enabled=False)

    await harness.run_ingest()

    assert "StageCacheHook" not in harness.calls
    assert harness.kwargs_of("runner.run")["cache_hook"] is None


# ------------------------------------------------------------------ dequeue skip
@pytest.mark.parametrize("status", [JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED])
async def test_an_already_terminal_job_is_skipped_after_one_read(make_harness, status) -> None:
    from types import SimpleNamespace  # noqa: PLC0415

    harness = make_harness(existing_job=SimpleNamespace(status=status))

    await harness.run_ingest()

    assert harness.calls == ["jobs.get"]
    assert harness.transitions == []


# ------------------------------------------------------------------ cooperative cancel
async def test_cooperative_cancel_probes_the_flag_then_force_terminates_without_raising(
    make_harness,
) -> None:
    """The guard re-reads the cancel flag at the root START; JobCancelledError → CANCELLED, no re-raise."""
    harness = make_harness(root_node_ids=("n1",), cancel_requested=True)

    async def _fire_root_start(kwargs) -> None:
        await kwargs["progress_callback"](
            ProgressEvent(phase=ProgressPhase.START, node_id="n1", kind="intake")
        )

    harness.run_behaviour = _fire_root_start

    await harness.run_ingest()  # does NOT raise: arq must not retry an operator cancel

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_FULL,
        "StageCacheHook",
        "runner.run",
        "jobs.is_cancel_requested",
        "jobs.force_terminate",
    ]
    assert harness.transitions == [
        "job: RUNNING",
        "document: PROCESSING",
        "job + document: CANCELLED",
    ]
    assert harness.kwargs_of("jobs.force_terminate")["reason"].startswith("cancelled: cancelled at")


# ------------------------------------------------------------------ hard cancel (CancelledError)
async def test_hard_cancel_writes_both_terminal_rows_then_reraises(make_harness) -> None:
    harness = make_harness()
    harness.fail_on("runner.run", asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_FULL,
        "StageCacheHook",
        "runner.run",
        "ingestion.mark_failed",
        "jobs.mark_failed",
    ]
    assert harness.args_of("ingestion.mark_failed") == (harness.document_id,)
    failed = harness.kwargs_of("jobs.mark_failed")
    assert failed["error_type"] == "CancelledError"
    assert failed["error"].startswith("cancelled or timed out")
    assert "failed_node_id" not in failed


async def test_hard_cancel_terminal_write_survives_a_second_cancel_then_reraises(
    make_harness,
) -> None:
    """The shielded write is driven to completion even when a SECOND cancel lands inside it."""
    harness = make_harness()
    harness.fail_on("runner.run", asyncio.CancelledError())
    started, release = asyncio.Event(), asyncio.Event()
    original = harness.database.ingestion.mark_failed

    async def _blocking_document_write(*args, **kwargs) -> None:
        started.set()
        await release.wait()
        await original(*args, **kwargs)

    harness.database.ingestion.mark_failed = _blocking_document_write

    task = asyncio.ensure_future(harness.run_ingest())
    await started.wait()
    task.cancel()  # the second cancellation, racing the shielded terminal write
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert harness.calls[-2:] == ["ingestion.mark_failed", "jobs.mark_failed"]


# ------------------------------------------------------------------ generic failure
async def test_run_failure_persists_the_partial_tree_then_marks_both_failed_and_reraises(
    make_harness,
) -> None:
    harness = make_harness()
    breadcrumb = FailureBreadcrumb(
        node_id="parse",
        node_kind="docling",
        error_type="TimeoutError",
        message="slow",
        item_index=3,
    )
    partial = object()
    harness.fail_on(
        "runner.run",
        PipelineRunError(
            "pipeline run failed: provider https://user:s3cret@llm.example/v1 down",
            breadcrumb=breadcrumb,
            record=partial,
        ),
    )

    with pytest.raises(PipelineRunError):
        await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_FULL,
        "StageCacheHook",
        "runner.run",
        "jobs.persist_execution_tree",
        "ingestion.mark_failed",
        "jobs.mark_failed",
    ]
    assert harness.args_of("jobs.persist_execution_tree") == (harness.job_id, partial)
    assert harness.transitions == [
        "job: RUNNING",
        "document: PROCESSING",
        "document: FAILED",
        "job: FAILED",
    ]


async def test_run_failure_stamps_the_breadcrumb_columns_and_redacts_the_error(
    make_harness,
) -> None:
    harness = make_harness()
    breadcrumb = FailureBreadcrumb(
        node_id="parse",
        node_kind="docling",
        error_type="TimeoutError",
        message="slow",
        item_index=3,
    )
    harness.fail_on(
        "runner.run",
        PipelineRunError(
            "pipeline run failed: provider https://user:s3cret@llm.example/v1 down",
            breadcrumb=breadcrumb,
        ),
    )

    with pytest.raises(PipelineRunError):
        await harness.run_ingest()

    failed = harness.kwargs_of("jobs.mark_failed")
    assert (
        failed["failed_node_id"],
        failed["failed_node_kind"],
        failed["failed_item_index"],
        failed["error_type"],
    ) == ("parse", "docling", 3, "TimeoutError")
    assert "s3cret" not in failed["error"]
    assert failed["error"].startswith(
        "PipelineRunError: pipeline run failed: provider https://***@"
    )
    assert failed["finished_at"] is not None


async def test_failure_before_the_run_has_no_tree_no_breadcrumb_and_the_exception_type(
    make_harness,
) -> None:
    """A rehydrate failure (document row missing): no partial tree, breadcrumb columns None."""
    harness = make_harness()
    harness.database.documents.get = harness._async("documents.get", None)

    with pytest.raises(RuntimeError, match="not found"):
        await harness.run_ingest()

    assert harness.calls == [*_CLAIM, "documents.get", "ingestion.mark_failed", "jobs.mark_failed"]
    failed = harness.kwargs_of("jobs.mark_failed")
    assert failed["failed_node_id"] is None
    assert failed["failed_node_kind"] is None
    assert failed["failed_item_index"] is None
    assert failed["error_type"] == "RuntimeError"


async def test_a_failing_partial_tree_persist_never_masks_the_job_failure(make_harness) -> None:
    harness = make_harness()
    harness.fail_on("runner.run", PipelineRunError("boom", record=object()))
    harness.fail_on("jobs.persist_execution_tree", RuntimeError("persist hiccup"))

    with pytest.raises(PipelineRunError, match="boom"):
        await harness.run_ingest()

    assert harness.calls[-3:] == [
        "jobs.persist_execution_tree",
        "ingestion.mark_failed",
        "jobs.mark_failed",
    ]


async def test_a_persist_failure_after_the_run_marks_both_failed_and_skips_done(
    make_harness,
) -> None:
    """The one-tx save fails after the blobs landed: FAILED on both truths, no index, no DONE."""
    harness = make_harness()
    harness.fail_on("ingestion.save", RuntimeError("tx aborted"))

    with pytest.raises(RuntimeError, match="tx aborted"):
        await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_FULL,
        "StageCacheHook",
        "runner.run",
        "jobs.persist_execution_tree",
        "RunTranslator.translate",
        "ingestion.store_blobs",
        "ingestion.save",
        "ingestion.mark_failed",
        "jobs.mark_failed",
    ]


async def test_a_denormalisation_hiccup_after_the_index_still_ends_done(make_harness) -> None:
    harness = make_harness()
    harness.fail_on("filters.sync_document_filter_payloads", RuntimeError("hiccup"))

    await harness.run_ingest()

    assert harness.calls[-3:] == [
        "filters.sync_document_filter_payloads",
        "meta_vectors.sync_document_meta_vectors",
        "jobs.mark_done",
    ]


# ------------------------------------------------------------------ the replay branch (ingest side)
async def test_replay_job_rehydrates_without_s3_then_delegates_to_replay_run(
    make_harness, monkeypatch
) -> None:
    harness = make_harness(existing_job=replay_job("chunk"))
    harness.stub_replay_run(monkeypatch)

    await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        "documents.get",
        "collections.get",
        "collections.get_schema",
        "documents.get_metadata",
        "ReplayRun.execute",
    ]
    assert "runner.run" not in harness.calls


async def test_replay_failure_fails_the_job_and_only_warns_the_document(
    make_harness, monkeypatch
) -> None:
    harness = make_harness(existing_job=replay_job("chunk"))
    harness.stub_replay_run(monkeypatch)
    harness.fail_on("ReplayRun.execute", RuntimeError("embed exploded"))

    with pytest.raises(RuntimeError, match="embed exploded"):
        await harness.run_ingest()

    assert harness.calls[-3:] == [
        "ReplayRun.execute",
        "ingestion.mark_replay_failed",
        "jobs.mark_failed",
    ]
    assert "ingestion.mark_failed" not in harness.calls
    assert harness.transitions[-2:] == [
        "document: status kept, replay-failure warning stamped",
        "job: FAILED",
    ]


async def test_replay_hard_cancel_also_keeps_the_document_status(make_harness, monkeypatch) -> None:
    harness = make_harness(existing_job=replay_job("embed"))
    harness.stub_replay_run(monkeypatch)
    harness.fail_on("ReplayRun.execute", asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await harness.run_ingest()

    assert harness.calls[-3:] == [
        "ReplayRun.execute",
        "ingestion.mark_replay_failed",
        "jobs.mark_failed",
    ]
    assert harness.kwargs_of("jobs.mark_failed")["error_type"] == "CancelledError"
