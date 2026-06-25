# ====== Code Summary ======
# StageEngine — thin orchestrator for the P2/P3/P4 pipeline.
# Runs S0 → S1 → S2 → S4 → S5 → S6 by delegating to S012Runner and S456Runner.
# Merkle-DAG fingerprinting and node caching are handled inside S012Runner.  Per-run stage
# resolution from PipelineConfig is delegated to StageResolver (stage_resolver.py).
#
# Heavy stage logic is in sibling modules:
#   result.py        — EngineResult dataclass
#   deps.py          — StageDeps frozen container
#   s012_runner.py   — S0/S1/S2 execution + persist_s012
#   s456_runner.py   — S4/S5/S6 execution + S6 trace flush
#   stage_resolver.py — per-run stage stack resolution
#   cache_io.py      — node-cache read/write + S3 restore/encode
#   s6_builder.py    — builds a per-run S6 stage from the collection embed config
#   trace_flush.py   — assembles implicit_meta + flushes embed-chain traces
#
# REFACTOR EXCEPTION (>200 lines): all heavy logic is extracted; the remaining length is the
# public API surface — a 15-parameter constructor and a 10-parameter run() — both of which
# carry mandatory Google-style docstrings per project rules.  The executable body of run()
# is ~30 lines of glue.  Splitting the docstrings from the signatures is not possible.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.pipeline.assembly import ProviderRegistry
    from common_libs.storage.s3.client import S3Client

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig
from common_libs.pipeline.caches.node_cache import NodeCache
from common_libs.pipeline.caches.provider_cache import ProviderCallCache
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage
from common_libs.pipeline.stages.s2_enrich import S2EnrichStage
from common_libs.pipeline.stages.s4_chunk import S4ChunkStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.repositories import (
    BlockRepository,
    ChunkRepository,
    DocumentRepository,
)
from common_libs.storage.qdrant.client import QdrantStorageClient
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .deps import StageDeps
from .result import EngineResult
from .s012_persist import S012PersistHelpers
from .s012_runner import S012Runner
from .s456_runner import S456Runner
from .stage_resolver import StageResolver


class StageEngine(LoggerClass):
    """
    P2/P3/P4 stage engine: S0 → S1 → S2 → S4 → S5 → S6 with Merkle-DAG caching.

    Responsibilities:
    1. Accept all stage and infrastructure dependencies at construction.
    2. Create StageDeps, S012Runner, and S456Runner on init.
    3. run() resolves the effective stage stack (via StageResolver), then delegates to
       the runners.

    All S0/S1/S2 execution and Postgres persistence logic lives in S012Runner.
    All S4/S5/S6 execution logic lives in S456Runner.
    Heavy helpers (stage_resolver, cache_io, s6_builder, trace_flush) are sibling modules.
    """

    def __init__(
        self,
        s0: S0IngestStage,
        s1: S1ParseStage,
        s3: S3Client,
        postgres: PostgresClient,
        node_cache: NodeCache,
        provider_cache: ProviderCallCache,
        document_repo: DocumentRepository,
        block_repo: BlockRepository,
        chunk_repo: ChunkRepository | None = None,
        s2: S2EnrichStage | None = None,
        s4: S4ChunkStage | None = None,
        s5: S5ContextualizeStage | None = None,
        s6: S6EmbedIndexStage | None = None,
        registry: ProviderRegistry | None = None,
        qdrant: QdrantStorageClient | None = None,
    ) -> None:
        """
        Initialize the engine with its stage and infrastructure dependencies.

        Args:
            s0 (S0IngestStage): Ingestion + conversion stage (always present).
            s1 (S1ParseStage): Parsing + rasterization stage (always present).
            s3 (S3Client): SeaweedFS object store client.
            postgres (PostgresClient): Postgres session factory.
            node_cache (NodeCache): Node-level cache backed by the stage_run table.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            document_repo (DocumentRepository): Document status update operations.
            block_repo (BlockRepository): IR block persistence operations.
            chunk_repo (ChunkRepository | None): Chunk persistence (P4).
            s2 (S2EnrichStage | None): Enrichment stage (P3).
            s4 (S4ChunkStage | None): Chunking stage; s5 contextualizes; s6 embeds + indexes (P4).
            s5 (S5ContextualizeStage | None): Contextualization stage (P4).
            s6 (S6EmbedIndexStage | None): Default embed + index stage (P4).
            registry (ProviderRegistry | None): Resolves per-run PipelineConfig into stages.
            qdrant (QdrantStorageClient | None): Live Qdrant client for per-run S6 builds.
        """
        LoggerClass.__init__(self)
        self._s0 = s0
        self._s1 = s1
        self._s2 = s2
        self._s4 = s4
        self._s5 = s5
        self._s6 = s6
        self._s3 = s3
        self._registry = registry
        self._qdrant = qdrant

        # Build the frozen deps container and the two runners
        self._deps = StageDeps(
            s3=s3,
            postgres=postgres,
            node_cache=node_cache,
            provider_cache=provider_cache,
            document_repo=document_repo,
            block_repo=block_repo,
            chunk_repo=chunk_repo,
        )
        self._s012 = S012Runner(self._deps)
        self._s456 = S456Runner(self._deps)

    # ─── Public entry point ────────────────────────────────────────────────────

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
        Execute the full pipeline (S0 → S1 → S2 → S4 → S5 → S6) for a document.

        Args:
            doc_id (uuid.UUID): Document primary key (pre-created in Postgres).
            source_hash (str): SHA-256 hex of the original file (content address).
            filename (str): Original filename (extension determines conversion path).
            pipeline_version (str): Collection pipeline version tag.
            file_bytes (bytes | None): Raw file bytes; downloaded from S3 when None.
            collection_id (str | None): Qdrant collection name for S6 indexing.
            pipeline_config (PipelineConfig | None): Per-run overrides; None = use defaults.
            metadata_fields (list | None): Per-collection metadata field specs for S6.
            doc_user_meta (dict | None): User-supplied business metadata for S6.
            progress_cb (Callable | None): Optional coarse-progress hook invoked at each stage
                boundary with ``(stage_node_id, percent)``. Telemetry only — never affects the
                run. The worker wires this to live job-progress updates; ``None`` = no reporting.

        Returns:
            EngineResult: Stage results + fingerprints + cache-hit flags + budget spent.
        """
        async def _report(stage: str, percent: int) -> None:
            """Invoke the optional progress hook, swallowing any telemetry-side failure."""
            if progress_cb is None:
                return
            try:
                await progress_cb(stage, percent)
            except Exception as exc:  # telemetry must never break the pipeline
                self.logger.warning(f"progress_cb failed at {stage} ({exc}).")
        self.logger.info(
            f"Engine.run: doc_id={doc_id} source_hash={source_hash[:8]}… "
            f"configured={pipeline_config is not None}"
        )

        # 1. Resolve effective stage stack for this run
        s0, s1, s2, s4, s5, s6 = StageResolver.resolve(
            pipeline_config,
            self._deps,
            self._registry,
            self._qdrant,
            (self._s0, self._s1, self._s2, self._s4, self._s5, self._s6),
        )

        # 2. Download original bytes if not provided (arq worker path)
        if file_bytes is None:
            file_bytes = await self._deps.s3.download(S3Helpers.key_original(source_hash))
            self.logger.debug(f"Downloaded original from S3: key_original={source_hash[:8]}…")

        # 3. Run S0/S1/S2 with Merkle-DAG node caching (report progress at each boundary)
        s0_result, s0_fp, s0_cache_hit = await self._s012.run_s0(
            s0, doc_id, source_hash, filename, file_bytes
        )
        await _report("s0", 15)
        s1_result, ir, s1_fp, s1_cache_hit = await self._s012.run_s1(
            s1, doc_id, source_hash, s0_result, s0_fp
        )
        await _report("s1", 35)
        s2_result, final_ir, s2_fp, s2_cache_hit = await self._s012.run_s2(
            s2, doc_id, source_hash, s1_result, ir, s1_fp
        )
        await _report("s2", 55)

        # 4. Persist blocks + finalize document in Postgres.
        # Fail-closed: this step runs outside the S0/S1/S2 (guarded_run) and S4/S5/S6
        # (run_s456) guards, so a failure here would otherwise leave the document stuck in
        # ``processing``. Mark it ``failed`` before re-raising (the secondary status write is
        # best-effort inside mark_failed and never masks the original persist error).
        try:
            await S012PersistHelpers.persist_s012(
                self._deps, doc_id, source_hash, s0_result, s1_result, s1_fp, s0_fp,
                s2_result, s2_fp, final_ir, s1_cache_hit, s2_cache_hit,
            )
        except Exception as exc:
            self.logger.error(
                f"persist_s012 failed for doc_id={doc_id} "
                f"({type(exc).__name__}: {exc}) — marking document 'failed'."
            )
            await S012PersistHelpers.mark_failed(self._deps, doc_id)
            raise
        await _report("persist", 65)

        # 5. Run S4/S5/S6 (chunk → contextualize → embed + index).
        # On any failure here the runner flips the document to ``failed`` and re-raises.
        s4_result, s5_result, s6_result = await self._s456.run_s456(
            s4, s5, s6, final_ir, collection_id, s0_result, doc_id,
            metadata_fields, doc_user_meta
        )
        await _report("s6", 95)

        # 6. Terminal success: flip the document from ``parsed`` to ``done`` ONLY now that
        # chunks (and, when a collection is set, the Qdrant upsert) have persisted.
        await S012PersistHelpers.mark_done(self._deps, doc_id)

        # 7. Log completion and assemble result
        self.logger.info(f"Engine.run done: doc_id={doc_id}")

        return EngineResult(
            s0_result=s0_result,
            s1_result=s1_result,
            s2_result=s2_result,
            s4_result=s4_result,
            s5_result=s5_result,
            s6_result=s6_result,
            stage_fingerprints={"s0": s0_fp, "s1": s1_fp, "s2": s2_fp},
            from_cache={"s0": s0_cache_hit, "s1": s1_cache_hit, "s2": s2_cache_hit},
            budget_spent=s2_result.budget_spent if s2_result is not None else 0.0,
        )
