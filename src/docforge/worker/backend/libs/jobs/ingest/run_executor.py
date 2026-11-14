# ====== Code Summary ======
# RunExecutor — the "run the pipeline" step shared by the full run and the replay run: the live
# progress chain (JobProgressRecorder wrapped by the cooperative-cancel CancellationGuard), the
# stage-cache hook (built only when the cache is enabled AND the run is not a forced full recompute)
# and the PipelineRunner call with the worker's preflight / egress / trace settings. A full run hands
# the cache hook, a replay hands the resume point — never both, exactly as before the extraction.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Callable
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import TraceLevel
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.reachability import ProviderEgressPolicy
from shared_libs.public_models import CollectionContract, SourceDocument

# ====== Local Project Imports ======
from ..cancellation import CancellationGuard
from ..progress import JobProgressRecorder
from .ingest_services import IngestServices


class RunExecutor:
    """Build the progress chain / cache hook and run the PipelineRunner."""

    def __init__(self, services: IngestServices, cache_hook_factory: Callable[..., Any]) -> None:
        """
        Args:
            services (IngestServices): The run's services (runner, config, logger, database).
            cache_hook_factory (Callable[..., Any]): ``StageCacheHook`` — called as
                ``(blob, collection_id, doc_uuid, database)`` to build the stage-cache hook.
        """
        self._services = services
        self._cache_hook_factory = cache_hook_factory

    @staticmethod
    def root_ids(blob: dict) -> list[str]:
        """The blob's top-level node ids (the traced stage boundaries)."""
        return [node.get("id", "") for node in blob.get("nodes", [])]

    @staticmethod
    def guarded_progress(
        job_id: uuid.UUID, blob: dict, collection: Any, planned_ids: list[str]
    ) -> CancellationGuard:
        """
        Build the live-progress callback: the recorder keeps the job row current (START = stage
        running now, END = percentage + one trace row) — root nodes only — and the guard re-reads the
        job's cancel flag at each root-stage boundary, raising JobCancelledError between nodes.

        The denominator is the PLANNED (happy-path) subset — escalation/fallback stages that run only
        on a bad outcome are excluded so the percentage is not understated by never-run nodes;
        ``root_ids`` stays every top-level id so a step that DOES run is still traced. The meter
        prices against the collection's EFFECTIVE rates (canonical defaults folded with its
        per-collection overrides) — the SAME numbers the pre-hoc estimator used.

        Args:
            job_id (uuid.UUID): The job row driving the lifecycle.
            blob (dict): The normalized pipeline blob.
            collection (Any): The collection row (``estimate_overrides``).
            planned_ids (list[str]): The root stage ids that count toward the percentage.

        Returns:
            CancellationGuard: The progress callback to hand the runner.
        """
        root_ids = RunExecutor.root_ids(blob)
        rates = RateTable.from_overrides(collection.estimate_overrides)
        recorder = JobProgressRecorder(job_id, root_ids, planned_ids, rates)
        return CancellationGuard(job_id, root_ids, recorder)

    def build_cache_hook(
        self, blob: dict, collection_id: uuid.UUID, doc_uuid: uuid.UUID, force: bool
    ) -> Any | None:
        """
        Build the stage-cache hook, or None.

        Attached ONLY when enabled AND this is not a forced full recompute. When it is None the
        engine runs byte-for-byte as if the cache did not exist. A cacheable stage (parse) is served
        from / stored into the per-collection cache; the report surfaces hit/miss/stored.
        """
        if self._services.config.WORKER_CACHE_ENABLED and not force:
            return self._cache_hook_factory(blob, collection_id, doc_uuid, self._services.database)
        return None

    def _base_kwargs(
        self, timeout_seconds: float, progress_callback: Any, trace_level: TraceLevel
    ) -> dict[str, Any]:
        """The runner settings both run modes share (preflight, egress policy, trace level)."""
        config = self._services.config
        return {
            "timeout_seconds": timeout_seconds,
            "progress_callback": progress_callback,
            "preflight_enabled": config.WORKER_PREFLIGHT_ENABLED,
            "preflight_cache_ttl_seconds": config.WORKER_PREFLIGHT_CACHE_TTL_SECONDS,
            "egress_policy": ProviderEgressPolicy.from_spec(config.PROVIDER_EGRESS_ALLOWLIST),
            "trace_level": trace_level,
        }

    async def run_full(
        self,
        blob: dict,
        source: SourceDocument,
        contract: CollectionContract,
        *,
        timeout_seconds: float,
        progress_callback: Any,
        trace_level: TraceLevel,
        cache_hook: Any | None,
        document_id: str,
    ) -> tuple[Any, Any]:
        """
        Run the whole graph on the fresh input, then log the stage-cache report when there is one.

        Args:
            blob (dict): The normalized pipeline blob.
            source (SourceDocument): The run input (filename, bytes, declared metadata).
            contract (CollectionContract): The collection contract.
            timeout_seconds (float): The wall-clock job timeout.
            progress_callback (Any): The guarded progress callback.
            trace_level (TraceLevel): The effective trace level.
            cache_hook (Any | None): The stage-cache hook (None → no cache).
            document_id (str): The document id, for the cache-report log line.

        Returns:
            tuple[Any, Any]: ``(bundle, record)`` as the runner delivers them.
        """
        bundle, record = await self._services.runner.run(
            blob,
            source,
            contract,
            **self._base_kwargs(timeout_seconds, progress_callback, trace_level),
            cache_hook=cache_hook,
        )
        if cache_hook is not None and cache_hook.report:
            self._services.logger.info(
                f"Stage cache for document {document_id}: {cache_hook.report}"
            )
        return bundle, record

    async def run_replay(
        self,
        blob: dict,
        source: SourceDocument,
        contract: CollectionContract,
        *,
        timeout_seconds: float,
        progress_callback: Any,
        trace_level: TraceLevel,
        resume: Any,
    ) -> tuple[Any, Any]:
        """Run ONLY the downstream subgraph on the seeds (no cache: parse never runs)."""
        return await self._services.runner.run(
            blob,
            source,
            contract,
            **self._base_kwargs(timeout_seconds, progress_callback, trace_level),
            resume=resume,
        )


__all__ = ["RunExecutor"]
