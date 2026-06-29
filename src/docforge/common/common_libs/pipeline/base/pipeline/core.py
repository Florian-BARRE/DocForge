# ====== Code Summary ======
# AbstractPipeline — the top level of Pipeline -> Stage -> Step, and the ENGINE itself (there is
# no separate engine module). run(ctx) walks its topologically-ordered stages and, per stage,
# applies the common middleware: compute the Merkle node fingerprint (node_type=stage.key,
# code_version=NODE_VERSION, params=stage.fingerprint_params(), inputs=upstream-producer fps);
# NODE_CACHED → consult/populate the node cache via the injected hooks (skip on hit); else run;
# wrap every run fail-closed and dispatch the stage's declarative ON_ERROR; emit progress + unified
# tracking. All environment-specific I/O (cache read/write, persistence, collection gate, original
# bytes) is delegated to EngineHooks, so the loop stays generic and the worker injects byte-identical
# behavior. describe() recurses into stages -> steps -> providers.
#
# REFACTOR EXCEPTION (>200 lines): this is one cohesive engine — topo ordering, fingerprinting, the
# per-stage cache/track middleware, ON_ERROR dispatch, and describe() form a single abstraction that
# would only fragment if split. The overage is dominated by the mandatory contract docstrings.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipeline.base.stage.core import AbstractStage
from common_libs.pipeline.base.stage.model import CachePolicy, ErrorPolicy
from common_libs.pipeline.bricks.tracking import ExecutionTrace
from common_libs.pipeline.caches.fingerprint import compute_fingerprint

# ====== Local Project Imports ======
from .hooks import EngineHooks
from .model import PipelineSchema

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext

# Type of the optional coarse-progress hook: ``(stage_key, percent) -> awaitable``.
ProgressCb = Callable[[str, int], Awaitable[None]]


class AbstractPipeline(ABC, LoggerClass):
    """
    Universal pipeline contract — and the fingerprint/cache/track/error engine driving every stage.

    Concrete pipelines declare only ``KEY``/``NAME``/``DESCRIPTION`` and supply their stage set;
    ``run`` walks them in topological order applying the common middleware, then the stage's
    declarative ``ON_ERROR`` policy on any exception. Environment-specific I/O (node-cache,
    persistence, the collection gate) is delegated to the injected ``EngineHooks`` (no-op by default,
    so the engine is fully functional standalone in tests).
    """

    KEY: ClassVar[str] = "pipeline"
    NAME: ClassVar[str] = "Pipeline"
    DESCRIPTION: ClassVar[str] = ""

    def __init__(
        self,
        stages: list[AbstractStage],
        *,
        progress_cb: ProgressCb | None = None,
        hooks: EngineHooks | None = None,
    ) -> None:
        """
        Initialise the pipeline with its (unordered) stage set.

        Args:
            stages (list[AbstractStage]): The stages to run; ordered topologically here.
            progress_cb (ProgressCb | None): Optional coarse-progress hook invoked at each stage
                boundary with ``(stage_key, percent)``. Telemetry only.
            hooks (EngineHooks | None): The I/O seam (node-cache, lifecycle, collection gate).
                Defaults to all-no-op ``EngineHooks`` (re-run every stage, no caching/persistence).

        Raises:
            ValueError: When a stage's ``AFTER`` references an unknown stage, or the dependency
                graph contains a cycle.
        """
        LoggerClass.__init__(self)
        self._stages = self._topo_order(list(stages))
        self._progress_cb = progress_cb
        self._hooks = hooks or EngineHooks()

    @property
    def stages(self) -> list[AbstractStage]:
        """The pipeline's stages in topological (execution) order."""
        return self._stages

    async def run(self, ctx: "PipelineContext") -> ExecutionTrace:
        """
        Execute every stage in topological order under the common middleware.

        Args:
            ctx (PipelineContext): The mutable run accumulator.

        Returns:
            ExecutionTrace: The hierarchical trace accumulated for this run.

        Raises:
            Exception: Re-raises a stage failure whose ``ON_ERROR`` is ``FAIL_DOC`` (fail-closed).
        """
        # 1. Open the run trace and perform one-time setup (e.g. download original bytes).
        trace = ExecutionTrace.for_context(ctx)
        trace.begin_pipeline(self.KEY, self.NAME)
        self.logger.info(f"Pipeline {self.KEY!r} started: stages={[s.key for s in self._stages]}")

        try:
            await self._hooks.prepare(ctx)

            # 2. Walk the stages; per stage fingerprint -> cache/run -> ON_ERROR -> progress.
            produced_by: dict[str, str] = {}
            total = len(self._stages) or 1
            for idx, stage in enumerate(self._stages, start=1):
                fingerprint = self._stage_fingerprint(stage, ctx, produced_by)
                ctx.fingerprints[stage.key] = fingerprint
                try:
                    await self._execute_stage(stage, ctx, fingerprint)
                except Exception as exc:
                    if not await self._handle_stage_error(stage, ctx, exc):
                        raise
                # Record this stage as the producer of its declared keys for downstream fingerprints.
                for key in stage.produces:
                    produced_by[key] = stage.key
                await self._report(stage.key, int(idx / total * 100))

            # 3. Terminal success — flip the document to ``done`` (no-op without hooks).
            await self._hooks.mark_done(ctx)
        finally:
            trace.end_pipeline()

        self.logger.info(f"Pipeline {self.KEY!r} done in {trace.duration_ms} ms.")
        return trace

    async def _execute_stage(
        self,
        stage: AbstractStage,
        ctx: "PipelineContext",
        fingerprint: str,
    ) -> None:
        """
        Apply the cache/skip middleware around a single stage, then run + tracking + cache store.

        Args:
            stage (AbstractStage): The stage to execute.
            ctx (PipelineContext): The mutable run accumulator.
            fingerprint (str): The stage's Merkle node fingerprint (cache key).
        """
        hooks = self._hooks

        # 1. Gate: a stage the hooks veto (e.g. embed/index without a collection) is skipped.
        # Checked before anything else so a gated stage incurs no cache read or 'running' marker.
        if not await hooks.should_run(stage, ctx):
            ctx.from_cache.setdefault(stage.key, False)
            self._record_synthetic_stage(ctx, stage, skipped=True)
            await hooks.on_skipped(stage, ctx)
            return

        # 2. NODE_CACHED: consult the cache FIRST — a hit must not be preceded by before_stage,
        # whose 'running' marker (node_cache.start) would otherwise delete the cached 'done' row
        # and turn every hit into a miss. On a hit, load the artefact into ctx and skip the run.
        if stage.cache_policy == CachePolicy.NODE_CACHED and await hooks.cache_load(stage, ctx, fingerprint):
            ctx.from_cache[stage.key] = True
            self._record_synthetic_stage(ctx, stage, cache_hit=True)
            await hooks.after_stage(stage, ctx)
            return

        # 3. Miss / idempotent-write: NOW fire the pre-run prep (mark 'running'/'processing', hydrate
        # inputs), run the stage (its own run() opens the trace), then store the NODE_CACHED artefact.
        ctx.from_cache.setdefault(stage.key, False)
        await hooks.before_stage(stage, ctx)
        await self._run_stage_tracked(stage, ctx)
        if stage.cache_policy == CachePolicy.NODE_CACHED:
            await hooks.cache_store(stage, ctx, fingerprint)
        await hooks.after_stage(stage, ctx)

    async def _run_stage_tracked(self, stage: AbstractStage, ctx: "PipelineContext") -> None:
        """
        Run a stage; the stage's own ``run`` opens its stage/step trace nodes.

        Args:
            stage (AbstractStage): The stage to execute.
            ctx (PipelineContext): The mutable run accumulator.
        """
        await stage.run(ctx)

    def _stage_fingerprint(
        self,
        stage: AbstractStage,
        ctx: "PipelineContext",
        produced_by: dict[str, str],
    ) -> str:
        """
        Compute the Merkle node fingerprint with the same wrapper as the legacy s012_runner.

        ``node_type`` is the stage's ``key`` (the canonical StageKey —
        the NODE_CACHED adapters pin the legacy ``s0``/``s1``/``s2`` ids), ``code_version`` its
        ``NODE_VERSION``, ``params`` its ``fingerprint_params()``, and the inputs are the
        fingerprints of the upstream stages that produce this stage's ``CONSUMES`` keys (deduped, in
        order). A root stage (all inputs externally-provided) is seeded with the content address
        (``ctx.source_hash``), matching the legacy S0 which chains off ``[source_hash]``.

        Args:
            stage (AbstractStage): The stage being fingerprinted.
            ctx (PipelineContext): The mutable run accumulator (carries upstream fingerprints).
            produced_by (dict[str, str]): Map of context key -> the upstream stage that produced it.

        Returns:
            str: The blake3 Merkle fingerprint for this node.
        """
        inputs: list[str] = []
        for key in stage.consumes:
            producer = produced_by.get(key)
            if producer is not None:
                upstream_fp = ctx.fingerprints.get(producer)
                if upstream_fp and upstream_fp not in inputs:
                    inputs.append(upstream_fp)
        if not inputs:
            # Root stage: seed with the content address (legacy S0 input = [source_hash]).
            inputs = [ctx.source_hash or ""]
        return compute_fingerprint(
            node_type=stage.key,
            code_version=stage.code_version,
            params=stage.fingerprint_params(),
            input_fingerprints=inputs,
        )

    def _record_synthetic_stage(
        self,
        ctx: "PipelineContext",
        stage: AbstractStage,
        *,
        cache_hit: bool = False,
        skipped: bool = False,
    ) -> None:
        """
        Record a stage trace node for a stage that did not run (cache hit or skipped).

        Args:
            ctx (PipelineContext): The mutable run accumulator.
            stage (AbstractStage): The stage that was bypassed.
            cache_hit (bool): True when bypassed via a node-cache hit.
            skipped (bool): True when bypassed via the ``should_run`` gate.
        """
        trace = ExecutionTrace.for_context(ctx)
        node = trace.begin_stage(stage.key, stage.name)
        node.cache_hit = cache_hit
        node.skipped = skipped
        node.succeeded = True
        trace.end_stage(node)

    async def _handle_stage_error(
        self,
        stage: AbstractStage,
        ctx: "PipelineContext",
        exc: Exception,
    ) -> bool:
        """
        Dispatch the stage's declarative ``ON_ERROR`` policy after it raised.

        Args:
            stage (AbstractStage): The stage that raised.
            ctx (PipelineContext): The mutable run accumulator.
            exc (Exception): The exception the stage raised.

        Returns:
            bool: True when the run may continue (SKIP / DEGRADE); False to propagate (FAIL_DOC).
        """
        trace = ExecutionTrace.for_context(ctx)
        trace.mark_last_stage_error(f"{type(exc).__name__}: {exc}")
        await self._hooks.on_error(stage, ctx, exc)

        # 1. FAIL_DOC — fail-closed: mark the doc failed (hook) and propagate.
        if stage.error_policy == ErrorPolicy.FAIL_DOC:
            self.logger.error(
                f"Stage {stage.key!r} failed ({type(exc).__name__}: {exc}) — "
                f"ON_ERROR=fail_doc -> marking failed + propagating."
            )
            await self._hooks.mark_failed(ctx)
            return False

        # 2. SKIP — drop the stage's output and continue.
        if stage.error_policy == ErrorPolicy.SKIP:
            trace.mark_last_stage_skipped()
            self.logger.warning(
                f"Stage {stage.key!r} failed ({type(exc).__name__}: {exc}) — "
                f"ON_ERROR=skip -> continuing without its output."
            )
            return True

        # 3. DEGRADE — continue in a degraded state (partial / no output).
        if stage.error_policy == ErrorPolicy.DEGRADE:
            trace.mark_last_stage_degraded()
            self.logger.warning(
                f"Stage {stage.key!r} failed ({type(exc).__name__}: {exc}) — "
                f"ON_ERROR=degrade -> continuing degraded."
            )
            return True

        return False

    async def _report(self, stage_key: str, percent: int) -> None:
        """
        Invoke the optional progress hook, swallowing any telemetry-side failure.

        Args:
            stage_key (str): The stage that just completed.
            percent (int): Coarse completion percentage.
        """
        if self._progress_cb is None:
            return
        try:
            await self._progress_cb(stage_key, percent)
        except Exception as exc:  # telemetry must never break the pipeline
            self.logger.warning(f"progress_cb failed at {stage_key} ({exc}).")

    def describe(self) -> PipelineSchema:
        """
        Emit the self-describing schema for the whole pipeline, recursing into stages.

        Returns:
            PipelineSchema: Identity + stage schemas (each recursing into steps + providers).
        """
        return PipelineSchema(
            key=self.KEY,
            name=self.NAME,
            description=self.DESCRIPTION,
            stages=[stage.describe() for stage in self._stages],
        )

    @staticmethod
    def _topo_order(stages: list[AbstractStage]) -> list[AbstractStage]:
        """
        Topologically order stages by their ``AFTER`` edges (Kahn's algorithm, stable).

        Among stages that are simultaneously ready, declaration order is preserved so the ordering
        is deterministic.

        Args:
            stages (list[AbstractStage]): The unordered stage set.

        Returns:
            list[AbstractStage]: The stages in a valid execution order.

        Raises:
            ValueError: On an unknown ``AFTER`` reference or a dependency cycle.
        """
        # 1. Index stages by key and validate every AFTER edge resolves.
        by_key: dict[str, AbstractStage] = {s.key: s for s in stages}
        for stage in stages:
            for dep in stage.after:
                if dep not in by_key:
                    raise ValueError(
                        f"Stage {stage.key!r} declares AFTER={dep!r} but no such stage exists."
                    )

        # 2. Kahn's algorithm, preserving declaration order among ready stages.
        remaining = list(stages)
        resolved: list[str] = []
        ordered: list[AbstractStage] = []
        while remaining:
            ready = [s for s in remaining if all(dep in resolved for dep in s.after)]
            if not ready:
                cyclic = ", ".join(s.key for s in remaining)
                raise ValueError(f"Cycle in stage dependency graph among: {cyclic}.")
            for stage in ready:
                ordered.append(stage)
                resolved.append(stage.key)
                remaining.remove(stage)
        return ordered


__all__ = ["AbstractPipeline"]
