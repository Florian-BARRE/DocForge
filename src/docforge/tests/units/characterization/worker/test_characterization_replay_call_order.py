# ====== Code Summary ======
# CHARACTERIZATION of the replay branch (``ReplayRun.execute``, reached through ``ingest_document`` for a
# job whose ``replay_from`` is set): the exact ordered facade / store calls of a replay and the arguments
# that shape them. The pure engine pieces (graph build, ReplayPlanner, ReplaySeeder) are replaced by
# fakes returning REAL ReplayPlan / SeedNeed values, so only the worker's own orchestration is pinned.
# Golden lists record what the code does TODAY; a change is a decision, never a test to "fix".

# ====== Third-Party Library Imports ======
import pytest
from characterization_ingest_harness import IngestHarness, replay_job

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.replay import ReplayUnsupportedError, SeedKind, SeedNeed
from shared_libs.pipelines.ingest.stages import StageKey

_CLAIM = ["jobs.get", "jobs.mark_running", "ingestion.mark_processing"]
# ingest_document's rehydrate for a replay: NO S3 read (the replay stands on the persisted IR).
_REHYDRATE_REPLAY = [
    "documents.get",
    "collections.get",
    "collections.get_schema",
    "documents.get_metadata",
]
_INDEX_TAIL = [
    "ingestion.index",
    "filters.sync_document_filter_payloads",
    "meta_vectors.sync_document_meta_vectors",
    "jobs.mark_done",
]


@pytest.fixture
def make_harness(monkeypatch, jobs_core, jobs_replay, jobs_cancellation):
    """Factory of a wired IngestHarness whose job is a replay (graph/planner/seeder faked)."""

    def _make(
        *,
        stage: StageKey = StageKey.CHUNK,
        needs: tuple[SeedNeed, ...] = (),
        needs_crops: bool = False,
        **options,
    ) -> IngestHarness:
        harness = IngestHarness(
            monkeypatch,
            jobs_core,
            jobs_replay,
            jobs_cancellation,
            existing_job=replay_job(stage.value),
            **options,
        )
        harness.plan_replay(monkeypatch, stage=stage, needs=needs, needs_crops=needs_crops)
        return harness

    return _make


def _need(kind: SeedKind) -> SeedNeed:
    return SeedNeed(node_id="up", field_name="f", kind=kind)


async def test_replay_with_no_seeds_loads_only_the_ir_then_runs_persists_indexes_and_finishes(
    make_harness,
) -> None:
    harness = make_harness()

    await harness.run_ingest()

    assert harness.calls == [
        *_CLAIM,
        *_REHYDRATE_REPLAY,
        "PipelineBuilder.build",
        "ReplayPlanner.plan",
        "replay_source.load_ir",
        "replay_source.ingest_facts",
        "ReplaySeeder.resume_point",
        "runner.run",
        "jobs.persist_execution_tree",
        "RunTranslator.translate",
        "replay_persist.save_downstream",
        *_INDEX_TAIL,
    ]


async def test_replay_loads_chunks_and_document_meta_only_when_the_plan_needs_them(
    make_harness,
) -> None:
    harness = make_harness(needs=(_need(SeedKind.CHUNKS), _need(SeedKind.DOCUMENT_META)))

    await harness.run_ingest()

    persisted_loads = [name for name in harness.calls if name.startswith("replay_source.")]
    assert persisted_loads == [
        "replay_source.load_ir",
        "replay_source.load_chunks",
        "replay_source.load_document_meta",
        "replay_source.ingest_facts",
    ]


async def test_replay_loads_the_ir_with_crops_only_when_the_plan_needs_crops(make_harness) -> None:
    harness = make_harness(stage=StageKey.ENRICH, needs_crops=True)

    await harness.run_ingest()

    assert harness.kwargs_of("replay_source.load_ir") == {"with_crops": True}


async def test_replay_runs_the_engine_with_the_resume_point_and_no_cache_hook(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    run_kwargs = harness.kwargs_of("runner.run")
    assert run_kwargs["resume"] is harness.resume
    assert "cache_hook" not in run_kwargs
    assert "StageCacheHook" not in harness.calls
    assert "documents.read_source_bytes" not in harness.calls


async def test_replay_downstream_save_replaces_enrichments_only_for_the_enrich_stage(
    make_harness,
) -> None:
    chunk = make_harness(stage=StageKey.CHUNK)
    await chunk.run_ingest()
    enrich = make_harness(stage=StageKey.ENRICH)
    await enrich.run_ingest()

    assert chunk.kwargs_of("replay_persist.save_downstream")["replace_enrichments"] is False
    assert enrich.kwargs_of("replay_persist.save_downstream")["replace_enrichments"] is True


async def test_replay_with_zero_chunks_saves_a_warning_and_skips_the_index(make_harness) -> None:
    harness = make_harness(chunks=0, points=0)

    await harness.run_ingest()

    assert harness.calls[-2:] == ["replay_persist.save_downstream", "jobs.mark_done"]
    assert "0 chunks" in harness.kwargs_of("replay_persist.save_downstream")["warning_reason"]


async def test_replay_with_chunks_saves_no_warning(make_harness) -> None:
    harness = make_harness(chunks=2)

    await harness.run_ingest()

    assert harness.kwargs_of("replay_persist.save_downstream")["warning_reason"] is None


async def test_replay_full_trace_stores_payloads_before_persisting_the_tree(make_harness) -> None:
    harness = make_harness(trace_verbosity="full", trace_ceiling="full")

    await harness.run_ingest()

    calls = harness.calls
    assert calls.index("ingestion.store_trace_payloads") == calls.index("runner.run") + 1
    assert calls.index("jobs.persist_execution_tree") == calls.index("runner.run") + 2


async def test_replay_status_transitions_never_touch_the_document_status(make_harness) -> None:
    harness = make_harness()

    await harness.run_ingest()

    assert harness.transitions == [
        "job: RUNNING",
        "document: PROCESSING",
        "document: replay layers saved (DONE kept)",
        "job: DONE",
    ]


async def test_replay_run_failure_persists_the_partial_tree_then_fails_job_and_warns_document(
    make_harness,
) -> None:
    from runner import PipelineRunError  # noqa: PLC0415

    harness = make_harness()
    partial = object()
    harness.fail_on("runner.run", PipelineRunError("embed down", record=partial))

    with pytest.raises(PipelineRunError):
        await harness.run_ingest()

    assert harness.calls[-4:] == [
        "runner.run",
        "jobs.persist_execution_tree",
        "ingestion.mark_replay_failed",
        "jobs.mark_failed",
    ]
    assert harness.args_of("jobs.persist_execution_tree") == (harness.job_id, partial)
    assert "ingestion.mark_failed" not in harness.calls


async def test_replay_without_a_persisted_ir_fails_before_any_run(make_harness) -> None:
    harness = make_harness()
    harness.database.replay_source.load_ir = harness._async("replay_source.load_ir", None)

    with pytest.raises(RuntimeError, match="no persisted IR"):
        await harness.run_ingest()

    assert "runner.run" not in harness.calls
    assert harness.calls[-3:] == [
        "replay_source.load_ir",
        "ingestion.mark_replay_failed",
        "jobs.mark_failed",
    ]


async def test_replay_of_a_stage_the_pipeline_no_longer_supports_fails_before_loading_anything(
    make_harness, monkeypatch
) -> None:
    harness = make_harness()

    class _Refusing:
        @staticmethod
        def plan(group, stage):
            harness._log("ReplayPlanner.plan", (group, stage), {})
            raise ReplayUnsupportedError("stage removed")

    monkeypatch.setattr(harness.jobs_replay, "ReplayPlanner", _Refusing)

    with pytest.raises(RuntimeError, match="no longer possible"):
        await harness.run_ingest()

    assert harness.calls[-4:] == [
        "PipelineBuilder.build",
        "ReplayPlanner.plan",
        "ingestion.mark_replay_failed",
        "jobs.mark_failed",
    ]
    assert not any(name.startswith("replay_source.") for name in harness.calls)
