# ====== Code Summary ======
# EngineHooks — the injection seam between the generic AbstractPipeline engine loop and the
# environment-specific I/O it must perform (node-cache read/write, document lifecycle, the
# collection-id gate, original-bytes prep). The base is an all-no-op default so AbstractPipeline.run
# is fully functional standalone (re-runs every stage, no caching, no persistence) — used by unit
# tests. The worker injects a concrete subclass (WorkerEngineHooks) that reuses the existing
# CacheIOHelpers / S012PersistHelpers so the wired dynamic path is byte-identical to the legacy one.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.base.stage.core import AbstractStage
    from common_libs.pipeline.stages.context import PipelineContext


class EngineHooks:
    """
    No-op default hooks for the AbstractPipeline engine loop.

    Every method is a no-op (or a permissive default) so the engine runs end-to-end without any
    infrastructure. Concrete deployments override the methods they need:

    - ``prepare``: one-time setup before the first stage (e.g. download original bytes).
    - ``before_stage`` / ``after_stage``: per-stage epilogues (e.g. PDF hydration; persist-after-enrich).
    - ``should_run``: per-stage gate (e.g. skip embed/index when no collection is set).
    - ``on_skipped``: side effect when ``should_run`` returned False (e.g. persist chunks PG-only).
    - ``cache_load`` / ``cache_store``: NODE_CACHED artefact read/write keyed by the node fingerprint.
    - ``on_error`` / ``mark_failed`` / ``mark_done``: failure + terminal lifecycle.
    """

    async def prepare(self, ctx: "PipelineContext") -> None:
        """One-time setup before the first stage runs."""
        return None

    async def before_stage(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """Run immediately before a stage executes (after its fingerprint is computed)."""
        return None

    async def after_stage(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """Run immediately after a stage completes successfully (or is served from cache)."""
        return None

    async def should_run(self, stage: "AbstractStage", ctx: "PipelineContext") -> bool:
        """Return False to skip a stage (the engine then calls ``on_skipped``)."""
        return True

    async def on_skipped(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """Side effect for a stage skipped by ``should_run`` (e.g. PG-only persistence)."""
        return None

    async def cache_load(
        self, stage: "AbstractStage", ctx: "PipelineContext", fingerprint: str
    ) -> bool:
        """Load a NODE_CACHED stage's artefact into ctx. Return True on hit, False on miss."""
        return False

    async def cache_store(
        self, stage: "AbstractStage", ctx: "PipelineContext", fingerprint: str
    ) -> None:
        """Persist a freshly-run NODE_CACHED stage's artefact under its fingerprint."""
        return None

    async def on_error(
        self, stage: "AbstractStage", ctx: "PipelineContext", exc: Exception
    ) -> None:
        """Run when a stage raises, before the ON_ERROR policy is applied (e.g. mark node failed)."""
        return None

    async def mark_failed(self, ctx: "PipelineContext") -> None:
        """Flip the document to ``failed`` (fail-closed terminal state)."""
        return None

    async def mark_done(self, ctx: "PipelineContext") -> None:
        """Flip the document to the terminal ``done`` state after every stage succeeded."""
        return None


__all__ = ["EngineHooks"]
