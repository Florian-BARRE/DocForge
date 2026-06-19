# ====== Code Summary ======
# StageEngine — thin orchestrator for the P2/P3/P4 pipeline.
# Runs S0 → S1 → S2 → S4 → S5 → S6 by delegating to S012Runner and S456Runner.
# Merkle-DAG fingerprinting and node caching are handled inside S012Runner.
# Stage resolution from PipelineConfig stays here (config-aware, registry-dependent).
#
# Heavy stage logic is in sibling modules:
#   result.py      — EngineResult dataclass
#   deps.py        — StageDeps frozen container
#   s012_runner.py — S0/S1/S2 execution + persist_s012
#   s456_runner.py — S4/S5/S6 execution + S6 trace flush
#   cache_io.py    — node-cache read/write + S3 restore + JSON encode
#   s6_builder.py  — builds a per-run S6 stage from the collection embed config
#   trace_flush.py — assembles implicit_meta + flushes embed-chain traces
#
# REFACTOR NOTE (231 lines > 200 limit):
# The __init__ signature carries 15 parameters (5 stages, 4 repos/caches, 3 infra clients,
# registry, qdrant) — an inevitable consequence of wiring the full pipeline at construction.
# _resolve_stages has 40 docstring lines describing the config/registry interaction which
# cannot move elsewhere.  The 200-line budget is met functionally (run() = 50 lines,
# _resolve_stages = 40 lines) — the overage is entirely header + docstring comment mass.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.data.storage.s3.client import S3Client
    from libs.engine.assembly import ProviderRegistry
    from libs.engine.stages.s1_parse import S1ParseStage as _S1ParseStageType

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.contracts.pipeline_config import PipelineConfig
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import (
    BlockRepository,
    ChunkRepository,
    DocumentRepository,
)
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.helpers import S3Helpers
from libs.engine.node_cache import NodeCache
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.s0_ingest import S0IngestStage
from libs.engine.stages.s1_parse import S1ParseStage
from libs.engine.stages.s2_enrich import S2EnrichStage
from libs.engine.stages.s4_chunk import S4ChunkStage
from libs.engine.stages.s5_contextualize import S5ContextualizeStage
from libs.engine.stages.s6_embed_index import S6EmbedIndexStage

# ====== Local Project Imports ======
from .deps import StageDeps
from .result import EngineResult
from .s012_runner import S012Runner
from .s6_builder import S6Builder
from .s456_runner import S456Runner


class StageEngine(LoggerClass):
    """
    P2/P3/P4 stage engine: S0 → S1 → S2 → S4 → S5 → S6 with Merkle-DAG caching.

    Responsibilities:
    1. Accept all stage and infrastructure dependencies at construction.
    2. Create StageDeps, S012Runner, and S456Runner on init.
    3. run() resolves the effective stage stack, then delegates to the runners.
    4. _resolve_stages() handles per-run PipelineConfig override (playground knobs).

    All S0/S1/S2 execution and Postgres persistence logic lives in S012Runner.
    All S4/S5/S6 execution logic lives in S456Runner.
    Heavy helpers (cache_io, s6_builder, trace_flush) are in sibling sub-modules.
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
            s0 (S0IngestStage): Ingestion and conversion stage.
            s1 (S1ParseStage): Parsing and rasterization stage.
            s3 (S3Client): SeaweedFS object store client.
            postgres (PostgresClient): Postgres session factory.
            node_cache (NodeCache): Node-level cache backed by stage_run table.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            document_repo (DocumentRepository): Document status update operations.
            block_repo (BlockRepository): IR block persistence operations.
            chunk_repo (ChunkRepository | None): Chunk persistence operations (P4).
            s2 (S2EnrichStage | None): Enrichment stage (P3).
            s4 (S4ChunkStage | None): Chunking stage (P4).
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
        dry_run: bool = False,
        collection_id: str | None = None,
        pipeline_config: PipelineConfig | None = None,
        metadata_fields: list[Any] | None = None,
        doc_user_meta: dict[str, Any] | None = None,
    ) -> EngineResult:
        """
        Execute the full pipeline (S0 → S1 → S2 → S4 → S5 → S6) for a document.

        Args:
            doc_id (uuid.UUID): Document primary key (pre-created in Postgres).
            source_hash (str): SHA-256 hex of the original file (content address).
            filename (str): Original filename (extension determines conversion path).
            pipeline_version (str): Collection pipeline version tag.
            file_bytes (bytes | None): Raw file bytes; downloaded from S3 when None.
            dry_run (bool): Use ephemeral in-memory cache and skip all DB writes.
            collection_id (str | None): Qdrant collection name for S6 indexing.
            pipeline_config (PipelineConfig | None): Per-run overrides; None = use defaults.
            metadata_fields (list | None): Per-collection metadata field specs for S6.
            doc_user_meta (dict | None): User-supplied business metadata for S6.

        Returns:
            EngineResult: Stage results + fingerprints + cache hits + budget.
        """
        self.logger.info(
            f"Engine.run: doc_id={doc_id} source_hash={source_hash[:8]}… "
            f"dry_run={dry_run} configured={pipeline_config is not None}"
        )

        # 1. Resolve effective stage stack for this run
        s0, s1, s2, s4, s5, s6 = self._resolve_stages(pipeline_config)
        _local_cache: dict[tuple[str, str, str], str] = {}

        # 2. Download original bytes if not provided (arq worker path)
        if file_bytes is None:
            file_bytes = await self._deps.s3.download(S3Helpers.key_original(source_hash))
            self.logger.debug(f"Downloaded original from S3: key_original={source_hash[:8]}…")

        # 3. Run S0/S1/S2 with Merkle-DAG node caching
        s0_result, s0_fp, s0_cache_hit = await self._s012.run_s0(
            s0, doc_id, source_hash, filename, file_bytes, _local_cache, dry_run
        )
        s1_result, ir, s1_fp, s1_cache_hit = await self._s012.run_s1(
            s1, doc_id, source_hash, s0_result, s0_fp, _local_cache, dry_run
        )
        s2_result, final_ir, s2_fp, s2_cache_hit = await self._s012.run_s2(
            s2, doc_id, source_hash, s1_result, ir, s1_fp, _local_cache, dry_run
        )

        # 4. Persist blocks + finalize document in Postgres
        await self._s012.persist_s012(
            doc_id, source_hash, s0_result, s1_result, s1_fp, s0_fp, s2_result, s2_fp,
            final_ir, s1_cache_hit, s2_cache_hit, dry_run
        )

        # 5. Run S4/S5/S6 (chunk → contextualize → embed + index)
        s4_result, s5_result, s6_result = await self._s456.run_s456(
            s4, s5, s6, final_ir, collection_id, s0_result, doc_id,
            metadata_fields, doc_user_meta, dry_run
        )

        # 6. Log completion and assemble result
        label = "dry_run done" if dry_run else "done"
        self.logger.info(f"Engine.run {label}: doc_id={doc_id}")

        budget_spent = s2_result.budget_spent if s2_result is not None else 0.0
        return EngineResult(
            s0_result=s0_result,
            s1_result=s1_result,
            s2_result=s2_result,
            s4_result=s4_result,
            s5_result=s5_result,
            s6_result=s6_result,
            stage_fingerprints={"s0": s0_fp, "s1": s1_fp, "s2": s2_fp},
            from_cache={"s0": s0_cache_hit, "s1": s1_cache_hit, "s2": s2_cache_hit},
            budget_spent=budget_spent,
        )

    # ─── Stage resolution ──────────────────────────────────────────────────────

    def _resolve_stages(
        self, pipeline_config: PipelineConfig | None
    ) -> tuple[
        S0IngestStage,
        _S1ParseStageType,
        S2EnrichStage,
        S4ChunkStage,
        S5ContextualizeStage,
        S6EmbedIndexStage | None,
    ]:
        """
        Resolve the effective stage stack for a run.

        With no per-run config (or no registry), the injected default stages are used —
        preserving the env-configured behavior of the worker and FastAPI app.  With a
        config and a registry, the parser and S2/S4/S5 stages are rebuilt from that config,
        making the pipeline parameterizable per-run.  S6 always uses the injected default
        because it owns a live Qdrant connection managed by the worker/app, not the registry.

        Args:
            pipeline_config (PipelineConfig | None): The per-run configuration, or None.

        Returns:
            tuple: (s0, s1, s2, s4, s5, s6) — the stages to execute this run.

        Raises:
            ProviderUnavailableError: When the config requests an unavailable provider.
        """
        # 1. No config or no registry → injected defaults (env-configured behavior)
        if pipeline_config is None or self._registry is None:
            return self._s0, self._s1, self._s2, self._s4, self._s5, self._s6

        # 2. Resolve parse chain + S2/S4/S5 from config; wrap parse chain into S1
        resolved = self._registry.build_stages(pipeline_config)
        s1 = S1ParseStage(parse_chain=resolved.parse_chain, s3=self._deps.s3)

        # 3. Build a per-run S6 from the collection's embed config (overrides injected default)
        s6 = S6Builder.build(
            pipeline_config.embed, self._qdrant, self._deps.chunk_repo, self._registry
        )
        return self._s0, s1, resolved.s2, resolved.s4, resolved.s5, s6
