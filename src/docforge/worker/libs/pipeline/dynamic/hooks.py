# ====== Code Summary ======
# WorkerEngineHooks — the concrete EngineHooks the worker injects into the dynamic AbstractPipeline
# engine. It reproduces the legacy ingestion lifecycle exactly, reusing the existing helpers so the
# dynamic path is byte-identical to the hand-wired StageEngine:
#   - prepare: download the original bytes if absent (fail-closed).
#   - before_stage: flip to 'processing' (ingest), mark the node 'running' + hydrate the PDF (parse).
#   - cache_load/cache_store: node-cache get/put via CacheDispatch (S0/S1/S2 artefacts).
#   - should_run/on_skipped: the collection_id gate — embed/index only with a collection, else PG-only.
#   - after_stage: persist_s012 after enrich (blocks + 'parsed'); flush embed traces after embed/index.
#   - on_error/mark_failed/mark_done: node 'failed' + document 'failed'/'done' (terminal lifecycle).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipeline.base.pipeline.hooks import EngineHooks
from common_libs.pipeline.base.stage.model import CachePolicy
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from ..orchestrator.cache_io import CacheIOHelpers
from ..orchestrator.deps import StageDeps as LegacyStageDeps
from ..orchestrator.s012_persist import S012PersistHelpers
from ..orchestrator.trace_flush import TraceFlusher
from .cache_dispatch import CacheDispatch

if TYPE_CHECKING:
    from common_libs.pipeline.base.stage.core import AbstractStage
    from common_libs.pipeline.stages.context import PipelineContext


class WorkerEngineHooks(EngineHooks, LoggerClass):
    """
    Worker-side EngineHooks reproducing the legacy ingest lifecycle for the dynamic engine.

    Holds the legacy ``StageDeps`` container (S3, Postgres, node cache, repos) and delegates every
    I/O concern to the existing helpers, so the dynamic engine reuses the exact persisted artefacts,
    cache keys, and document status transitions of the original hand-wired pipeline.
    """

    def __init__(self, deps: LegacyStageDeps) -> None:
        """
        Args:
            deps (LegacyStageDeps): The shared infra container (S3, Postgres, node cache, repos).
        """
        LoggerClass.__init__(self)
        self._deps = deps

    async def prepare(self, ctx: "PipelineContext") -> None:
        """Download the original bytes when absent (fail-closed: mark failed + re-raise)."""
        if ctx.original_bytes is not None:
            return
        try:
            ctx.original_bytes = await self._deps.s3.download(S3Helpers.key_original(ctx.source_hash))
        except Exception as exc:
            self.logger.error(
                f"Original download failed for doc_id={ctx.doc_id} "
                f"({type(exc).__name__}: {exc}) — marking document 'failed'."
            )
            await S012PersistHelpers.mark_failed(self._deps, ctx.doc_id)
            raise

    async def before_stage(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """Flip to 'processing' (ingest), mark the node 'running', and hydrate the PDF (parse)."""
        deps = self._deps
        # 1. Document enters 'processing' as the first stage begins (mirrors legacy run_s0).
        if stage.key == "ingest":
            async with deps.postgres.session() as session:
                await deps.document_repo.update_status(session, ctx.doc_id, "processing")

        # 2. Node-cached stages record a 'running' stage_run row keyed by the LEGACY node id
        # (stage.key = "s0"/"s1"/"s2") so the row matches the legacy engine. This fires only
        # on the post-miss/pre-run path (the engine calls before_stage after a cache miss), so the
        # 'running' marker never clobbers a cached 'done' row.
        if stage.cache_policy == CachePolicy.NODE_CACHED:
            async with deps.postgres.session() as session:
                await deps.node_cache.start(session, ctx.doc_id, stage.key, ctx.fingerprints[stage.key])

        # 3. Parse needs PDF bytes; hydrate from S3 when S0 was a cache hit (lazy pdf_bytes).
        if stage.key == "parse" and ctx.ingest_result is not None and ctx.ingest_result.pdf_bytes is None:
            ctx.ingest_result = await CacheIOHelpers.populate_pdf_bytes(deps.s3, ctx.ingest_result)

    async def should_run(self, stage: "AbstractStage", ctx: "PipelineContext") -> bool:
        """Gate embed/index on a collection being set; every other stage always runs."""
        if stage.key == "embed_index":
            return ctx.collection_id is not None
        return True

    async def on_skipped(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """When embed/index is skipped (no collection), persist chunks to Postgres only."""
        if stage.key != "embed_index":
            return
        if self._deps.chunk_repo is None or not ctx.chunks:
            return
        async with self._deps.postgres.session() as session:
            await self._deps.chunk_repo.bulk_insert(session, ctx.chunks)

    async def cache_load(
        self, stage: "AbstractStage", ctx: "PipelineContext", fingerprint: str
    ) -> bool:
        """Consult the node cache; on hit, restore the stage outputs onto the context."""
        # Node-cache row is keyed by the legacy node id (stage.key); the artefact codec is
        # dispatched by the semantic KEY (ingest/parse/enrich).
        ref = await CacheIOHelpers.check(
            self._deps.postgres, self._deps.node_cache, ctx.doc_id, stage.key, fingerprint
        )
        if ref is None:
            return False
        return await CacheDispatch.load(stage.key, self._deps.s3, ref, ctx)

    async def cache_store(
        self, stage: "AbstractStage", ctx: "PipelineContext", fingerprint: str
    ) -> None:
        """Upload the freshly-run stage's artefacts and record them in the node cache."""
        ref = await CacheDispatch.store(stage.key, self._deps.s3, ctx, fingerprint)
        if ref is not None:
            await CacheIOHelpers.store(
                self._deps.postgres, self._deps.node_cache, ctx.doc_id, stage.key, fingerprint, ref
            )

    async def after_stage(self, stage: "AbstractStage", ctx: "PipelineContext") -> None:
        """Persist the IR after enrich; flush embed-chain traces after embed/index."""
        if stage.key == "enrich":
            await self._persist_after_enrich(ctx)
        elif stage.key == "embed_index":
            await self._flush_embed_traces(ctx)

    async def on_error(
        self, stage: "AbstractStage", ctx: "PipelineContext", exc: Exception
    ) -> None:
        """Mark a node-cached stage's row 'failed' (mirrors the legacy guarded_run failure path)."""
        if stage.cache_policy != CachePolicy.NODE_CACHED:
            return
        fingerprint = ctx.fingerprints.get(stage.key)
        if not fingerprint:
            return
        async with self._deps.postgres.session() as session:
            await self._deps.node_cache.fail(session, ctx.doc_id, stage.key, fingerprint)

    async def mark_failed(self, ctx: "PipelineContext") -> None:
        """Flip the document to 'failed' (tolerant — never masks the original stage error)."""
        await S012PersistHelpers.mark_failed(self._deps, ctx.doc_id)

    async def mark_done(self, ctx: "PipelineContext") -> None:
        """Flip the document to the terminal 'done' status after every stage succeeded."""
        await S012PersistHelpers.mark_done(self._deps, ctx.doc_id)

    async def _persist_after_enrich(self, ctx: "PipelineContext") -> None:
        """Persist IR blocks + flip to 'parsed' (delegates to the legacy persist_s012)."""
        await S012PersistHelpers.persist_s012(
            self._deps,
            ctx.doc_id,
            ctx.source_hash,
            ctx.ingest_result,
            ctx.parse_result,
            ctx.fingerprints["parse"],
            ctx.fingerprints["ingest"],
            ctx.enrich_result,
            ctx.fingerprints["enrich"],
            ctx.ir,
            ctx.from_cache.get("parse", False),
            ctx.from_cache.get("enrich", False),
        )

    async def _flush_embed_traces(self, ctx: "PipelineContext") -> None:
        """Append the S6 embed-chain traces onto the document's implicit_meta (lineage parity)."""
        s6 = ctx.embed_result
        if s6 is None or not s6.chain_traces:
            return
        async with self._deps.postgres.session() as session:
            current = await self._deps.document_repo.get_by_id(session, ctx.doc_id)
            if current is None:
                return
            patched = TraceFlusher.build_embed_trace_patch(
                dict(current.implicit_meta or {}), s6.chain_traces
            )
            await self._deps.document_repo.update_status(
                session, ctx.doc_id, current.status, implicit_meta=patched
            )


__all__ = ["WorkerEngineHooks"]
