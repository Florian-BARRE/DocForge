# ====== Code Summary ======
# DynamicStageEngine — the worker-side driver that runs ingestion through the self-describing
# dynamic pipeline (assembly.build_pipeline + the AbstractPipeline engine). It is the SOLE ingestion
# engine; its run() signature + EngineResult shape match what tasks.py expects. Per run it builds the
# adapter-wrapped stage list from the (per-collection or default) PipelineConfig, reproduces the
# collection_id gate, threads a typed PipelineContext, and drives it with WorkerEngineHooks.
#
# IngestPipeline is the thin concrete AbstractPipeline (identity only — all logic is inherited);
# it now lives canonically in common_libs.pipeline.ingest and is re-exported here for back-compat.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig, build_default_pipeline
from common_libs.pipeline.assembly.stage_assembler import build_pipeline
from common_libs.pipeline.ingest import IngestPipeline
from common_libs.pipeline.stages.context import PipelineContext, StageDeps

# ====== Local Project Imports ======
from ..orchestrator.deps import StageDeps as LegacyStageDeps
from ..orchestrator.result import EngineResult
from .hooks import WorkerEngineHooks

if TYPE_CHECKING:
    from common_libs.pipeline.assembly import ProviderRegistry
    from common_libs.pipeline.caches.node_cache import NodeCache
    from common_libs.pipeline.caches.provider_cache import ProviderCallCache
    from common_libs.storage.postgres.client import PostgresClient
    from common_libs.storage.postgres.repositories import (
        BlockRepository,
        ChunkRepository,
        DocumentRepository,
    )
    from common_libs.storage.qdrant.client import QdrantStorageClient
    from common_libs.storage.s3.client import S3Client


class DynamicStageEngine(LoggerClass):
    """
    Drop-in replacement for StageEngine that drives the dynamic AbstractPipeline behind a flag.

    Holds the shared infrastructure + provider registry + Qdrant client; builds the stage list per
    run from the effective PipelineConfig and executes it via the generic engine with the worker's
    lifecycle hooks. The output (EngineResult) matches the legacy engine field-for-field.
    """

    def __init__(
        self,
        s3: S3Client,
        postgres: PostgresClient,
        node_cache: NodeCache,
        provider_cache: ProviderCallCache,
        document_repo: DocumentRepository,
        block_repo: BlockRepository,
        chunk_repo: ChunkRepository | None,
        registry: ProviderRegistry,
        qdrant: QdrantStorageClient | None,
        runtime_config: Any,
    ) -> None:
        """
        Args:
            s3 (S3Client): SeaweedFS object store client.
            postgres (PostgresClient): Postgres session factory.
            node_cache (NodeCache): Merkle-DAG node cache.
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            document_repo (DocumentRepository): Document status operations.
            block_repo (BlockRepository): IR block persistence.
            chunk_repo (ChunkRepository | None): Chunk persistence.
            registry (ProviderRegistry): Builds the inner chains/stages from config.
            qdrant (QdrantStorageClient | None): Live Qdrant client (embed/index), or None.
            runtime_config (Any): RUNTIME_CONFIG — default pipeline + S0 converter source.
        """
        LoggerClass.__init__(self)
        self._registry = registry
        self._qdrant = qdrant
        self._rc = runtime_config
        # Shared infra in BOTH shapes: the common StageDeps threads the ctx (S6 opens its own
        # session); the legacy StageDeps backs the lifecycle hooks (persist / node-cache / status).
        self._deps = StageDeps(
            s3=s3, postgres=postgres, qdrant=qdrant, node_cache=node_cache,
            provider_cache=provider_cache, document_repo=document_repo,
            block_repo=block_repo, chunk_repo=chunk_repo,
        )
        self._legacy_deps = LegacyStageDeps(
            s3=s3, postgres=postgres, node_cache=node_cache, provider_cache=provider_cache,
            document_repo=document_repo, block_repo=block_repo, chunk_repo=chunk_repo,
        )

    async def run(
        self,
        doc_id: uuid.UUID,
        source_hash: str,
        filename: str,
        pipeline_version: str,
        file_bytes: bytes | None = None,
        collection_id: str | None = None,
        pipeline_config: PipelineConfig | None = None,
        metadata_fields: list[Any] | None = None,
        doc_user_meta: dict[str, Any] | None = None,
        progress_cb: Callable[[str, int], Awaitable[None]] | None = None,
    ) -> EngineResult:
        """
        Execute the full pipeline for a document via the dynamic engine (StageEngine-compatible).

        Args: identical in meaning to ``StageEngine.run`` (doc_id … progress_cb).

        Returns:
            EngineResult: Per-stage results + fingerprints + cache-hit flags (legacy s0/s1/s2 keys).

        Raises:
            RuntimeError: When a collection is set but no embed/index stage exists (no Qdrant).
            Exception: Re-raises any FAIL_DOC stage failure (the document is marked failed first).
        """
        self.logger.info(
            f"DynamicEngine.run: doc_id={doc_id} source_hash={source_hash[:8]}... "
            f"configured={pipeline_config is not None} collection={collection_id}"
        )

        # 1. Resolve the effective config and build the ordered adapter-wrapped stage list.
        config = pipeline_config or build_default_pipeline(self._rc)
        stages = build_pipeline(config, self._registry, self._deps, self._qdrant, metadata_fields)

        # 2. Collection gate (build-time half): a collection set but no indexing stage = fail loudly.
        if collection_id is not None and not any(s.KEY == "embed_index" for s in stages):
            raise RuntimeError(
                f"S6 indexing required for collection {collection_id!r} but no embed provider / "
                f"Qdrant is available. Check the collection embed.provider config and QDRANT_HOST."
            )

        # 3. Thread a typed context and drive the generic engine with the worker lifecycle hooks.
        ctx = PipelineContext(
            deps=self._deps, doc_id=doc_id, source_hash=source_hash, filename=filename,
            file_bytes=file_bytes, collection_id=collection_id, metadata_fields=metadata_fields,
            doc_user_meta=doc_user_meta,
        )
        pipeline = IngestPipeline(stages, progress_cb=progress_cb, hooks=WorkerEngineHooks(self._legacy_deps))
        await pipeline.run(ctx)

        self.logger.info(f"DynamicEngine.run done: doc_id={doc_id}")
        return self._build_result(ctx)

    @staticmethod
    def _build_result(ctx: PipelineContext) -> EngineResult:
        """
        Assemble a legacy-shaped EngineResult from the accumulated context.

        Fingerprints + cache flags are re-keyed to the legacy ``s0``/``s1``/``s2`` ids so any
        downstream reader of EngineResult sees the same shape as the StageEngine produced.

        Args:
            ctx (PipelineContext): The accumulated run context.

        Returns:
            EngineResult: The aggregated run output.
        """
        key_map = {"s0": "ingest", "s1": "parse", "s2": "enrich"}
        return EngineResult(
            s0_result=ctx.s0_result,
            s1_result=ctx.s1_result,
            s2_result=ctx.s2_result,
            s4_result=ctx.s4_result,
            s5_result=ctx.s5_result,
            s6_result=ctx.s6_result,
            stage_fingerprints={legacy: ctx.fingerprints.get(new, "") for legacy, new in key_map.items()},
            from_cache={legacy: ctx.from_cache.get(new, False) for legacy, new in key_map.items()},
        )


__all__ = ["DynamicStageEngine", "IngestPipeline"]
