# ====== Code Summary ======
# IngestHarness — the recording fakes behind the ingest/replay CALL-ORDER characterization tests.
# Every Database facade method (the S3 read included, through ``documents``), the pipeline runner, the translator and the stage-cache
# hook factory append ONE entry to a shared ordered log (``"facade.method"``) when they are awaited /
# called, so a test can assert the EXACT ordered sequence of side effects of ``ingest_document`` (and of
# the replay branch) as a golden list. The fakes return what the real calls return and never touch a
# database, Redis or S3. Pure test support: it records what the code does TODAY, it prescribes nothing.

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.replay import ReplayPlan, SeedNeed
from shared_libs.pipelines.ingest.stages import StageKey
from shared_libs.services.db.postgresql.tables import JobStatus

# The facade calls that move a row to a terminal/lifecycle status, and the transition each one is.
# Used by ``IngestHarness.transitions`` to read the status story off the call log.
_TRANSITIONS: dict[str, str] = {
    "jobs.mark_running": "job: RUNNING",
    "ingestion.mark_processing": "document: PROCESSING",
    "ingestion.save": "document: DONE (or DONE with a 0-chunk warning)",
    "jobs.mark_done": "job: DONE",
    "ingestion.mark_failed": "document: FAILED",
    "ingestion.mark_replay_failed": "document: status kept, replay-failure warning stamped",
    "jobs.mark_failed": "job: FAILED",
    "jobs.force_terminate": "job + document: CANCELLED",
    "replay_persist.save_downstream": "document: replay layers saved (DONE kept)",
}


class _FakeS3:
    """The S3 handle: ``client()`` is an async context manager, ``bucket`` a name."""

    bucket = "bucket"

    def client(self):
        @asynccontextmanager
        async def _cm():
            yield MagicMock()

        return _cm()


class IngestHarness:
    """Wire ``jobs.core`` / ``jobs.replay`` / ``jobs.cancellation`` onto recording fakes for one run."""

    def __init__(
        self,
        monkeypatch: Any,
        jobs_core: Any,
        jobs_replay: Any,
        jobs_cancellation: Any,
        *,
        chunks: int = 1,
        points: int = 1,
        trace_verbosity: str = "shape",
        trace_ceiling: str = "shape",
        cache_enabled: bool = True,
        root_node_ids: tuple[str, ...] = (),
        existing_job: Any = None,
        cancel_requested: bool = False,
    ) -> None:
        """
        Args:
            monkeypatch (Any): The pytest monkeypatch (every patch is undone at teardown).
            jobs_core (Any): The ``jobs.core`` module under test.
            jobs_replay (Any): The ``jobs.replay`` module under test.
            jobs_cancellation (Any): The ``jobs.cancellation`` module (the guard's own CONTEXT).
            chunks (int): How many chunks the run's bundle delivers (0 = the zero-chunk warning path).
            points (int): How many Qdrant points the translated delivery carries (0 = no index step).
            trace_verbosity (str): The collection's ``trace_verbosity``.
            trace_ceiling (str): The operator ceiling ``WORKER_TRACE_MAX_VERBOSITY``.
            cache_enabled (bool): ``WORKER_CACHE_ENABLED``.
            root_node_ids (tuple[str, ...]): The normalized blob's top-level node ids.
            existing_job (Any): What ``jobs.get`` returns (None = a plain fresh job).
            cancel_requested (bool): What ``jobs.is_cancel_requested`` answers.
        """
        self.jobs_core = jobs_core
        self.jobs_replay = jobs_replay
        self._failures: dict[str, BaseException] = {}
        self._invocations: list[tuple[str, tuple, dict]] = []
        self.document_id = uuid.uuid4()
        self.collection_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.bundle = SimpleNamespace(chunks=[object()] * chunks, document_meta=None)
        self.record = MagicMock(name="execution-record")
        self.translated = SimpleNamespace(
            objects=[], blob_rows=[], payload=MagicMock(), points=[object()] * points, dense_dim=4
        )
        self.run_behaviour: Any = None
        self.cache_hook = SimpleNamespace(report=None)

        self.database = self._build_database(existing_job, cancel_requested)
        self.context = SimpleNamespace(
            database=self.database,
            s3=_FakeS3(),
            runner=SimpleNamespace(run=self._runner_run),
            worker_id="w1",
            job_timeout_seconds=30.0,
            RUNTIME_CONFIG=SimpleNamespace(
                WORKER_PREFLIGHT_ENABLED=True,
                WORKER_PREFLIGHT_CACHE_TTL_SECONDS=0.0,
                WORKER_JOB_TIMEOUT_MAX_SECONDS=7200.0,
                WORKER_CACHE_ENABLED=cache_enabled,
                PROVIDER_EGRESS_ALLOWLIST="",
                WORKER_TRACE_MAX_VERBOSITY=trace_ceiling,
                WORKER_TRACE_PAYLOAD_MAX_BYTES=1048576,
            ),
            logger=MagicMock(),
        )
        self._patch(
            monkeypatch, jobs_core, jobs_replay, jobs_cancellation, trace_verbosity, root_node_ids
        )

    # ---------------------------------------------------------------- the recording
    @property
    def calls(self) -> list[str]:
        """The ordered log of every recorded call (``"facade.method"``), oldest first."""
        return [name for name, _args, _kwargs in self._invocations]

    @property
    def transitions(self) -> list[str]:
        """The status story: the recorded calls that move a job/document row, in order."""
        return [_TRANSITIONS[name] for name in self.calls if name in _TRANSITIONS]

    def kwargs_of(self, name: str) -> dict:
        """The keyword arguments of the single recorded call ``name`` (fails if it ran 0 or 2+ times)."""
        matches = [kwargs for call, _args, kwargs in self._invocations if call == name]
        assert len(matches) == 1, f"{name} was recorded {len(matches)} times: {self.calls}"
        return matches[0]

    def args_of(self, name: str) -> tuple:
        """The positional arguments of the single recorded call ``name``."""
        matches = [args for call, args, _kwargs in self._invocations if call == name]
        assert len(matches) == 1, f"{name} was recorded {len(matches)} times: {self.calls}"
        return matches[0]

    def fail_on(self, name: str, error: BaseException) -> None:
        """Make the recorded call ``name`` raise ``error`` (after it is logged)."""
        self._failures[name] = error

    async def run_ingest(self, force: bool = False) -> None:
        """Await ``ingest_document`` for this harness's document and job ids."""
        await self.jobs_core.ingest_document({}, str(self.document_id), str(self.job_id), force)

    # ---------------------------------------------------------------- building the fakes
    def _log(self, name: str, args: tuple, kwargs: dict) -> None:
        self._invocations.append((name, args, kwargs))
        error = self._failures.get(name)
        if error is not None:
            raise error

    def _async(self, name: str, result: Any = None):
        async def _call(*args: Any, **kwargs: Any) -> Any:
            self._log(name, args, kwargs)
            return result

        return _call

    def _sync(self, name: str, result: Any = None):
        def _call(*args: Any, **kwargs: Any) -> Any:
            self._log(name, args, kwargs)
            return result

        return _call

    async def _runner_run(self, *args: Any, **kwargs: Any) -> tuple[Any, Any]:
        self._log("runner.run", args, kwargs)
        if self.run_behaviour is not None:
            await self.run_behaviour(kwargs)
        return self.bundle, self.record

    def _build_database(self, existing_job: Any, cancel_requested: bool) -> SimpleNamespace:
        self.document = SimpleNamespace(
            id=self.document_id,
            collection_id=self.collection_id,
            filename="f.pdf",
            source_hash="hash",
        )
        self.collection = SimpleNamespace(
            id=self.collection_id,
            name="c",
            supported_formats=["pdf"],
            max_file_size_bytes=100,
            job_timeout_seconds=None,
            trace_verbosity="shape",
            pipeline={"nodes": []},
            estimate_overrides=None,
        )
        a = self._async
        return SimpleNamespace(
            jobs=SimpleNamespace(
                get=a("jobs.get", existing_job),
                mark_running=a("jobs.mark_running"),
                mark_done=a("jobs.mark_done"),
                mark_failed=a("jobs.mark_failed"),
                force_terminate=a("jobs.force_terminate"),
                is_cancel_requested=a("jobs.is_cancel_requested", cancel_requested),
                persist_execution_tree=a("jobs.persist_execution_tree"),
            ),
            documents=SimpleNamespace(
                get=a("documents.get", self.document),
                get_metadata=a("documents.get_metadata", []),
                read_source_bytes=a("documents.read_source_bytes", b"raw-bytes"),
            ),
            collections=SimpleNamespace(
                get=a("collections.get", self.collection),
                get_schema=a("collections.get_schema", []),
            ),
            ingestion=SimpleNamespace(
                mark_processing=a("ingestion.mark_processing"),
                mark_failed=a("ingestion.mark_failed"),
                mark_replay_failed=a("ingestion.mark_replay_failed"),
                store_trace_payloads=a("ingestion.store_trace_payloads", {"ref": "x"}),
                store_blobs=a("ingestion.store_blobs"),
                save=a("ingestion.save"),
                index=a("ingestion.index"),
            ),
            filters=SimpleNamespace(
                sync_document_filter_payloads=a("filters.sync_document_filter_payloads")
            ),
            meta_vectors=SimpleNamespace(
                sync_document_meta_vectors=a("meta_vectors.sync_document_meta_vectors")
            ),
            replay_source=SimpleNamespace(
                load_ir=a("replay_source.load_ir", object()),
                load_chunks=a("replay_source.load_chunks", []),
                load_document_meta=a("replay_source.load_document_meta", None),
                ingest_facts=self._sync("replay_source.ingest_facts", object()),
            ),
            replay_persist=SimpleNamespace(save_downstream=a("replay_persist.save_downstream")),
        )

    def _patch(
        self,
        monkeypatch: Any,
        jobs_core: Any,
        jobs_replay: Any,
        jobs_cancellation: Any,
        trace_verbosity: str,
        root_node_ids: tuple[str, ...],
    ) -> None:
        self.collection.trace_verbosity = trace_verbosity
        # Each module resolves its services through its OWN module-level CONTEXT name.
        for module in (jobs_core, jobs_replay, jobs_cancellation):
            monkeypatch.setattr(module, "CONTEXT", self.context)
        # Blob normalization is characterized elsewhere: pass the stub blob through as-is.
        blob = {"nodes": [{"id": node_id, "kind": "intake"} for node_id in root_node_ids]}
        monkeypatch.setattr(jobs_core.BlobNormalizer, "normalize", lambda _stored: dict(blob))
        monkeypatch.setattr(
            jobs_core.RunTranslator,
            "translate",
            self._sync("RunTranslator.translate", self.translated),
        )
        monkeypatch.setattr(
            jobs_core, "StageCacheHook", self._sync("StageCacheHook", self.cache_hook)
        )

    def plan_replay(
        self,
        monkeypatch: Any,
        *,
        stage: StageKey = StageKey.CHUNK,
        needs: tuple[SeedNeed, ...] = (),
        needs_crops: bool = False,
    ) -> None:
        """Replace the replay module's graph build / planner / seeder (pure engine code) by fakes."""
        self.resume = object()
        plan = ReplayPlan(
            stage=stage,
            start_node_id=stage.value,
            downstream_ids=frozenset({stage.value}),
            needs=needs,
            needs_crops=needs_crops,
        )
        harness = self

        class _Builder:
            def build(self, blob: dict) -> Any:
                harness._log("PipelineBuilder.build", (blob,), {})
                return "group"

        class _Planner:
            @staticmethod
            def plan(group: Any, requested: str) -> ReplayPlan:
                harness._log("ReplayPlanner.plan", (group, requested), {})
                return plan

        class _Seeder:
            @staticmethod
            def resume_point(plan_: Any, group: Any, persisted: Any) -> Any:
                harness._log("ReplaySeeder.resume_point", (plan_, group, persisted), {})
                return harness.resume

        monkeypatch.setattr(self.jobs_replay, "PipelineBuilder", _Builder)
        monkeypatch.setattr(self.jobs_replay, "ReplayPlanner", _Planner)
        monkeypatch.setattr(self.jobs_replay, "ReplaySeeder", _Seeder)

    def stub_replay_run(self, monkeypatch: Any) -> None:
        """Replace ``ReplayRun.execute`` by a recording fake (isolates ingest_document's own side)."""
        monkeypatch.setattr(self.jobs_core.ReplayRun, "execute", self._async("ReplayRun.execute"))


def replay_job(stage: str = "chunk") -> SimpleNamespace:
    """The ``jobs.get`` answer of a not-yet-terminal REPLAY job (``replay_from`` set at admission)."""
    return SimpleNamespace(status=JobStatus.PENDING, replay_from=stage)
