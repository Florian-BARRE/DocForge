# ====== Code Summary ======
# StageEngine — P2/P3/P4 pipeline orchestrator with Merkle-DAG fingerprinting and double cache.
# Runs S0 → S1 → S2 → S4 → S5 → S6 with node-level caching for S0/S1/S2.
# S4/S5/S6 use Postgres/Qdrant idempotency instead of the Merkle node cache.
# dry_run mode uses an in-memory node cache and skips all Postgres/Qdrant writes.
#
# Heavy helper logic is delegated to sibling modules:
#   cache_io.py    — node-cache read/write + S3 restore + JSON encode
#   s6_builder.py  — builds a per-run S6 stage from the collection embed config
#   trace_flush.py — assembles implicit_meta + flushes embed-chain traces

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.engine.stages.s1_parse import S1ParseStage as _S1ParseStageType
    from libs.engine.assembly import ProviderRegistry

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.engine.fingerprint import compute_fingerprint
from libs.engine.node_cache import NodeCache
from libs.core.contracts.pipeline_config import PipelineConfig
from libs.engine.provider_cache import ProviderCallCache
from libs.engine.stages.s0_ingest import S0IngestStage, S0Result
from libs.engine.stages.s1_parse import S1ParseStage, S1Result
from libs.engine.stages.s2_enrich import S2EnrichStage, S2Result
from libs.engine.stages.s4_chunk import S4ChunkStage, S4Result
from libs.engine.stages.s5_contextualize import S5ContextualizeStage, S5Result
from libs.engine.stages.s6_embed_index import S6EmbedIndexStage, S6Result
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import BlockRepository, ChunkRepository, DocumentRepository
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.client import S3Client

# ====== Local Project Imports ======
from .cache_io import CacheIOHelpers
from .s6_builder import S6Builder
from .trace_flush import TraceFlusher

# ── Node version constants ────────────────────────────────────────────────────
# Increment these when the node's logic changes to invalidate stale cache entries.
# S4/S5/S6 do not use the Merkle node cache (idempotency via Postgres/Qdrant upserts).
_S0_NODE_VERSION: str = "1.0"
_S1_NODE_VERSION: str = "1.0"
_S2_NODE_VERSION: str = "1.0"


@dataclass(slots=True)
class EngineResult:
    """
    Aggregated output of a StageEngine pipeline run (S0 → S1 → S2 → S4 → S5 → S6).

    Carries per-stage results, Merkle fingerprints, cache hit flags, and budget spent.
    Stage results are None when their stage is disabled or not configured.
    """

    s0_result: S0Result
    s1_result: S1Result
    s2_result: S2Result | None = None          # None only when a cache error occurs
    s4_result: S4Result | None = None          # None only in dry_run (S4 is always built)
    s5_result: S5Result | None = None          # None only in dry_run (S5 is always built)
    s6_result: S6Result | None = None          # None when no collection_id or dry_run
    stage_fingerprints: dict[str, str] = field(default_factory=dict)
    from_cache: dict[str, bool] = field(default_factory=dict)
    budget_spent: float = 0.0                  # Total OCR/VLM API cost for this run


class StageEngine(LoggerClass):
    """
    P2/P3/P4 stage engine: S0 → S1 → S2 → S4 → S5 → S6 with Merkle-DAG caching.

    Responsibilities:
    1. Compute blake3 node fingerprint before each of S0/S1/S2.
    2. Consult NodeCache (stage_run table) — skip stage on cache hit, restore from S3.
    3. Execute the stage on miss, upload output meta JSON to S3, write cache entry.
    4. Persist IR blocks and update document status on successful completion.
    5. Run S4 (chunk) → S5 (contextualize) → S6 (embed + index) when configured.
    6. dry_run mode: ephemeral in-memory node cache, no Postgres writes, no block persist.

    Each Merkle node fingerprint = blake3(node_type, code_version, params, [input_fps]).
    S4/S5/S6 use Postgres/Qdrant idempotency instead of the Merkle node cache.
    S2 is optional: pass ``s2=None`` to run only S0→S1 (P1/P2 mode).
    S4/S5/S6 are optional: pass None to disable individual stages.

    Heavy helpers are in sibling sub-modules (cache_io, s6_builder, trace_flush).
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
        registry: "ProviderRegistry | None" = None,
        qdrant: QdrantStorageClient | None = None,
    ) -> None:
        """
        Initialize the engine with its stage and infrastructure dependencies.

        Args:
            s0 (S0IngestStage): Ingestion and conversion stage.
            s1 (S1ParseStage): Parsing and rasterization stage.
            s3 (S3Client): SeaweedFS object store client.
            postgres (PostgresClient): Postgres session factory (for intermediate commits).
            node_cache (NodeCache): Node-level cache backed by stage_run table.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            document_repo (DocumentRepository): Document status update operations.
            block_repo (BlockRepository): IR block persistence operations.
            chunk_repo (ChunkRepository | None): Chunk persistence operations (P4).
            s2 (S2EnrichStage | None): Enrichment stage (P3).  Always provided; None for legacy.
            s4 (S4ChunkStage | None): Chunking stage (P4).  Always provided; None for legacy.
            s5 (S5ContextualizeStage | None): Contextualization stage (P4).  Always provided.
            s6 (S6EmbedIndexStage | None): Default embed + index stage (P4).  Used as fallback
                when no per-run embed config is available.  None when Qdrant unavailable.
            registry (ProviderRegistry | None): Resolves a per-run PipelineConfig into
                concrete stages.  When provided, run(pipeline_config=...) overrides the
                injected default stages — this is what makes the playground parameterizable.
            qdrant (QdrantStorageClient | None): Live Qdrant client used to build per-run S6
                stages from the collection's embed config.  None when Qdrant is unavailable.
        """
        LoggerClass.__init__(self)
        self._s0 = s0
        self._s1 = s1
        self._s2 = s2
        self._s4 = s4
        self._s5 = s5
        self._s6 = s6
        self._s3 = s3
        self._postgres = postgres
        self._node_cache = node_cache
        self._provider_cache = provider_cache
        self._document_repo = document_repo
        self._block_repo = block_repo
        self._chunk_repo = chunk_repo
        self._registry = registry
        self._qdrant = qdrant

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

        Fingerprints S0/S1/S2 before execution and reads/writes the node cache.
        S4/S5/S6 run after S2 without node caching (idempotent via Postgres/Qdrant upserts).
        In dry_run mode, uses an ephemeral in-memory cache and skips all DB writes.

        Args:
            doc_id (uuid.UUID): Document primary key (pre-created in Postgres).
            source_hash (str): SHA-256 hex of the original file (content address).
            filename (str): Original filename (extension determines conversion path).
            pipeline_version (str): Collection pipeline version tag.
            file_bytes (bytes | None): Raw file bytes.  If None, the engine downloads
                the original from S3 (arq worker flow — file was uploaded at admission).
            dry_run (bool): When True, use in-memory node cache and skip all DB writes.
            collection_id (str | None): Qdrant collection name for S6 indexing.
                When None, S6 skips the Qdrant upsert (dry_run or retrieval disabled).
            pipeline_config (PipelineConfig | None): Per-run pipeline configuration.
                When provided (and a registry is configured), the parser and S2/S4/S5
                stages are resolved from this config for this run, overriding the
                injected defaults.  This is the mechanism behind playground knobs and
                per-collection pipelines.  None → use the engine's default stages.

        Returns:
            EngineResult: Stage results + per-stage fingerprints + cache hit flags + budget.
        """
        self.logger.info(
            f"Engine.run: doc_id={doc_id} source_hash={source_hash[:8]}… "
            f"dry_run={dry_run} configured={pipeline_config is not None}"
        )

        # 1. Resolve effective stage stack and prepare shared run state
        s0, s1, s2, s4, s5, s6 = self._resolve_stages(pipeline_config)
        _local_cache: dict[tuple[str, str, str], str] = {}

        # 2. Download original bytes if not provided (arq worker path)
        if file_bytes is None:
            file_bytes = await self._s3.download(S3Client.key_original(source_hash))
            self.logger.debug(f"Downloaded original from S3: key_original={source_hash[:8]}…")

        # 3. Run S0/S1/S2 with Merkle-DAG node caching
        s0_result, s0_fp, s0_cache_hit = await self._run_s0(
            s0, doc_id, source_hash, filename, file_bytes, _local_cache, dry_run
        )
        s1_result, ir, s1_fp, s1_cache_hit = await self._run_s1(
            s1, doc_id, source_hash, s0_result, s0_fp, _local_cache, dry_run
        )
        s2_result, final_ir, s2_fp, s2_cache_hit = await self._run_s2(
            s2, doc_id, source_hash, s1_result, ir, s1_fp, _local_cache, dry_run
        )

        # 4. Persist blocks + finalize document in Postgres
        await self._persist_s012(
            doc_id, source_hash, s0_result, s1_result, s1_fp, s0_fp, s2_result, s2_fp,
            final_ir, s1_cache_hit, s2_cache_hit, dry_run
        )

        # 5. Run S4/S5/S6 (chunk → contextualize → embed + index)
        s4_result, s5_result, s6_result = await self._run_s456(
            s4, s5, s6, final_ir, collection_id, s0_result, doc_id,
            metadata_fields, doc_user_meta, dry_run
        )

        # 6. Log completion and assemble result
        if not dry_run:
            self.logger.info(f"Engine.run done: doc_id={doc_id}")
        else:
            self.logger.info(f"Engine.run dry_run done: doc_id={doc_id}")

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

    # ─── Stage execution helpers ───────────────────────────────────────────────

    async def _run_s0(
        self,
        s0: S0IngestStage,
        doc_id: uuid.UUID,
        source_hash: str,
        filename: str,
        file_bytes: bytes,
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> tuple[S0Result, str, bool]:
        """
        Execute S0 (ingest + convert) with Merkle node caching.

        Args:
            s0 (S0IngestStage): S0 stage instance to execute on cache miss.
            doc_id (uuid.UUID): Document primary key.
            source_hash (str): SHA-256 of the original file (Merkle root).
            filename (str): Original filename.
            file_bytes (bytes): Raw file content.
            local_cache (dict): In-memory cache for dry_run mode.
            dry_run (bool): When True, skip all Postgres/S3 writes.

        Returns:
            tuple[S0Result, str, bool]: (result, fingerprint, cache_hit).
        """
        s0_fp = compute_fingerprint(
            node_type="s0",
            code_version=_S0_NODE_VERSION,
            params=self._s0_params(s0),
            input_fingerprints=[source_hash],
        )
        cached_ref = await CacheIOHelpers.check(
            self._postgres, self._node_cache, doc_id, "s0", s0_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S0 cache HIT: doc_id={doc_id}")
            return await CacheIOHelpers.restore_s0(self._s3, cached_ref), s0_fp, True

        # Cache miss: update status, execute, upload, commit
        if not dry_run:
            async with self._postgres.session() as session:
                await self._document_repo.update_status(session, doc_id, "processing")
                await self._node_cache.start(session, doc_id, "s0", s0_fp)
        try:
            result = await s0.run(file_bytes=file_bytes, filename=filename, doc_id=str(doc_id))
        except Exception:
            if not dry_run:
                async with self._postgres.session() as session:
                    await self._node_cache.fail(session, doc_id, "s0", s0_fp)
                    await self._document_repo.update_status(session, doc_id, "failed")
            raise

        s0_meta_key = S3Client.key_s0_meta(source_hash, s0_fp)
        await self._s3.upload(s0_meta_key, CacheIOHelpers.encode_s0_meta(result), "application/json")
        await CacheIOHelpers.store(
            self._postgres, self._node_cache, doc_id, "s0", s0_fp, s0_meta_key, local_cache, dry_run
        )
        return result, s0_fp, False

    async def _run_s1(
        self,
        s1: "_S1ParseStageType",
        doc_id: uuid.UUID,
        source_hash: str,
        s0_result: S0Result,
        s0_fp: str,
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> tuple[S1Result, Any, str, bool]:
        """
        Execute S1 (parse → IR + PNGs + crops) with Merkle node caching.

        Args:
            s1 (_S1ParseStageType): S1 stage instance to execute on cache miss.
            doc_id (uuid.UUID): Document primary key.
            source_hash (str): SHA-256 of the original file.
            s0_result (S0Result): Output from the S0 stage (may have lazy pdf_bytes).
            s0_fp (str): S0 Merkle fingerprint (chained as S1 input).
            local_cache (dict): In-memory cache for dry_run mode.
            dry_run (bool): When True, skip all Postgres/S3 writes.

        Returns:
            tuple[S1Result, DocumentIR, str, bool]: (result, ir, fingerprint, cache_hit).
        """
        from libs.core.ir.models import DocumentIR  # local import to avoid cycle

        s1_fp = compute_fingerprint(
            node_type="s1",
            code_version=_S1_NODE_VERSION,
            params=self._s1_params(s1),
            input_fingerprints=[s0_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            self._postgres, self._node_cache, doc_id, "s1", s1_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S1 cache HIT: doc_id={doc_id}")
            s1_result, ir = await CacheIOHelpers.restore_s1(self._s3, cached_ref)
            return s1_result, ir, s1_fp, True

        # Cache miss: hydrate pdf_bytes if lazy (S0 was a cache hit)
        if s0_result.pdf_bytes is None:
            s0_result = await CacheIOHelpers.populate_pdf_bytes(self._s3, s0_result)

        if not dry_run:
            async with self._postgres.session() as session:
                await self._node_cache.start(session, doc_id, "s1", s1_fp)
        try:
            s1_result = await s1.run(s0_result, fingerprint=s1_fp)
        except Exception:
            if not dry_run:
                async with self._postgres.session() as session:
                    await self._node_cache.fail(session, doc_id, "s1", s1_fp)
                    await self._document_repo.update_status(session, doc_id, "failed")
            raise

        ir = s1_result.ir
        ir_key = S3Client.key_ir(source_hash, s1_fp)
        await self._s3.upload(ir_key, ir.model_dump_json().encode("utf-8"), "application/json")
        s1_meta_key = S3Client.key_s1_meta(source_hash, s1_fp)
        await self._s3.upload(
            s1_meta_key, CacheIOHelpers.encode_s1_meta(s1_result, ir_key), "application/json"
        )
        await CacheIOHelpers.store(
            self._postgres, self._node_cache, doc_id, "s1", s1_fp, s1_meta_key, local_cache, dry_run
        )
        return s1_result, ir, s1_fp, False

    async def _run_s2(
        self,
        s2: S2EnrichStage,
        doc_id: uuid.UUID,
        source_hash: str,
        s1_result: S1Result,
        ir: Any,
        s1_fp: str,
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> tuple[S2Result | None, Any, str, bool]:
        """
        Execute S2 (enrich figures: OCR / VLM / chart-to-data) with Merkle node caching.

        Args:
            s2 (S2EnrichStage): S2 stage instance to execute on cache miss.
            doc_id (uuid.UUID): Document primary key.
            source_hash (str): SHA-256 of the original file.
            s1_result (S1Result): Output from the S1 stage.
            ir (DocumentIR): DocumentIR produced by S1.
            s1_fp (str): S1 Merkle fingerprint (chained as S2 input).
            local_cache (dict): In-memory cache for dry_run mode.
            dry_run (bool): When True, skip all Postgres/S3 writes.

        Returns:
            tuple[S2Result | None, DocumentIR, str, bool]: (result, final_ir, fingerprint, cache_hit).
        """
        s2_fp = compute_fingerprint(
            node_type="s2",
            code_version=_S2_NODE_VERSION,
            params=self._s2_params(s2),
            input_fingerprints=[s1_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            self._postgres, self._node_cache, doc_id, "s2", s2_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S2 cache HIT: doc_id={doc_id}")
            s2_result, final_ir = await CacheIOHelpers.restore_s2(self._s3, cached_ref)
            return s2_result, final_ir, s2_fp, True

        if not dry_run:
            async with self._postgres.session() as session:
                await self._node_cache.start(session, doc_id, "s2", s2_fp)
        try:
            s2_result = await s2.run(s1_result, ir)
        except Exception:
            if not dry_run:
                async with self._postgres.session() as session:
                    await self._node_cache.fail(session, doc_id, "s2", s2_fp)
                    await self._document_repo.update_status(session, doc_id, "failed")
            raise

        final_ir = s2_result.ir
        ir_enriched_key = S3Client.key_ir_enriched(source_hash, s2_fp)
        await self._s3.upload(
            ir_enriched_key, final_ir.model_dump_json().encode("utf-8"), "application/json"
        )
        s2_meta_key = S3Client.key_s2_meta(source_hash, s2_fp)
        await self._s3.upload(
            s2_meta_key, CacheIOHelpers.encode_s2_meta(s2_result, ir_enriched_key), "application/json"
        )
        await CacheIOHelpers.store(
            self._postgres, self._node_cache, doc_id, "s2", s2_fp, s2_meta_key, local_cache, dry_run
        )
        return s2_result, final_ir, s2_fp, False

    async def _persist_s012(
        self,
        doc_id: uuid.UUID,
        source_hash: str,
        s0_result: S0Result,
        s1_result: S1Result,
        s1_fp: str,
        s0_fp: str,
        s2_result: S2Result | None,
        s2_fp: str,
        final_ir: Any,
        s1_cache_hit: bool,
        s2_cache_hit: bool,
        dry_run: bool,
    ) -> None:
        """
        Persist IR blocks and update the document record to ``done`` in Postgres.

        Skips bulk_insert when both S1 and S2 were cache hits (blocks already stored).
        No-op in dry_run mode.

        Args:
            doc_id (uuid.UUID): Document primary key.
            source_hash (str): SHA-256 of the original file (used to derive S3 key).
            s0_result (S0Result): S0 output (contributes to implicit_meta).
            s1_result (S1Result): S1 output (contributes markdown_key to implicit_meta).
            s1_fp (str): S1 Merkle fingerprint.
            s0_fp (str): S0 Merkle fingerprint.
            s2_result (S2Result | None): S2 output, or None when S2 was skipped.
            s2_fp (str): S2 Merkle fingerprint.
            final_ir (DocumentIR): Enriched IR (or raw S1 IR when S2 skipped).
            s1_cache_hit (bool): True when S1 was a cache hit (blocks already stored).
            s2_cache_hit (bool): True when S2 was a cache hit.
            dry_run (bool): When True, skip all writes.
        """
        if dry_run:
            return

        # Blocks must only be inserted on the first run; cache hits mean they exist already.
        blocks_already_in_db = s1_cache_hit and (s2_result is None or s2_cache_hit)
        async with self._postgres.session() as session:
            if not blocks_already_in_db:
                await self._block_repo.bulk_insert(
                    session=session, document_id=doc_id, blocks=final_ir.blocks
                )
            await self._document_repo.update_status(
                session,
                doc_id,
                "done",
                page_count=final_ir.n_pages,
                language=final_ir.language,
                implicit_meta=TraceFlusher.build_implicit_meta(
                    s0_result=s0_result,
                    ir=final_ir,
                    s1_result=s1_result,
                    s0_fp=s0_fp,
                    s1_fp=s1_fp,
                    ir_key=S3Client.key_ir(source_hash, s1_fp),
                    s2_result=s2_result,
                    s2_fp=s2_fp,
                ),
            )

    async def _run_s456(
        self,
        s4: S4ChunkStage,
        s5: S5ContextualizeStage,
        s6: S6EmbedIndexStage | None,
        final_ir: Any,
        collection_id: str | None,
        s0_result: S0Result,
        doc_id: uuid.UUID,
        metadata_fields: list[Any] | None,
        doc_user_meta: dict[str, Any] | None,
        dry_run: bool,
    ) -> tuple[S4Result, S5Result, S6Result | None]:
        """
        Run S4 (chunk) → S5 (contextualize) → S6 (embed + index).

        S4 and S5 are pure IR transforms and run even in dry_run (playground preview).
        S6 only runs in live mode with a collection_id.

        Args:
            s4 (S4ChunkStage): Chunking stage.
            s5 (S5ContextualizeStage): Contextualization stage.
            s6 (S6EmbedIndexStage | None): Embed + index stage (None when Qdrant unavailable).
            final_ir (DocumentIR): IR produced by S0→S2 (may be enriched).
            collection_id (str | None): Qdrant collection name for indexing, or None.
            s0_result (S0Result): S0 output for doc_meta assembly.
            doc_id (uuid.UUID): Document primary key for trace flush.
            metadata_fields (list | None): Per-collection metadata field specs.
            doc_user_meta (dict | None): User-supplied business metadata.
            dry_run (bool): When True, skip S6 and all DB writes.

        Returns:
            tuple[S4Result, S5Result, S6Result | None]: Stage results.
        """
        # S4 and S5 always run (pure transforms — playground needs real chunk preview)
        s4_result: S4Result = await s4.run(final_ir)
        s5_result: S5Result = await s5.run(s4_result.chunks, final_ir)
        contextualized_chunks = s5_result.chunks

        s6_result: S6Result | None = None
        if dry_run or self._chunk_repo is None:
            return s4_result, s5_result, s6_result

        if s6 is not None and collection_id is not None:
            s6_result = await self._run_s6_and_flush_traces(
                s6, contextualized_chunks, collection_id, final_ir, s0_result,
                doc_id, metadata_fields, doc_user_meta
            )
        elif collection_id is not None:
            # collection_id is set but s6 is unavailable — fail loudly
            raise RuntimeError(
                f"S6 indexing required for collection {collection_id!r} "
                f"but no embed provider / Qdrant is available. "
                f"Check the collection embed.provider config and QDRANT_HOST connectivity."
            )
        else:
            # No collection → persist chunks to Postgres only (no Qdrant indexing)
            async with self._postgres.session() as session:
                await self._chunk_repo.bulk_insert(session, contextualized_chunks)

        return s4_result, s5_result, s6_result

    async def _run_s6_and_flush_traces(
        self,
        s6: S6EmbedIndexStage,
        chunks: list[Any],
        collection_id: str,
        final_ir: Any,
        s0_result: S0Result,
        doc_id: uuid.UUID,
        metadata_fields: list[Any] | None,
        doc_user_meta: dict[str, Any] | None,
    ) -> S6Result:
        """
        Run S6 (embed + index) and flush embed-chain traces onto the document record.

        Args:
            s6 (S6EmbedIndexStage): Embed + index stage.
            chunks (list): Contextualized chunks from S5.
            collection_id (str): Qdrant collection name.
            final_ir (DocumentIR): Final IR for doc_meta derivation.
            s0_result (S0Result): S0 output for implicit_meta fields.
            doc_id (uuid.UUID): Document primary key for trace flush.
            metadata_fields (list | None): Per-collection metadata field specs.
            doc_user_meta (dict | None): User-supplied business metadata.

        Returns:
            S6Result: S6 stage output.
        """
        doc_meta: dict[str, Any] = {
            **(s0_result.implicit_meta or {}),   # filename, extension, file_size, source_hash, page_count, has_scanned_pages
            "language": final_ir.language,       # detected at S1 (py3langid) — filterable system field
            "page_count": final_ir.n_pages,
            "n_blocks": len(final_ir.blocks),
            "n_figures": len(final_ir.figure_blocks),
            "n_tables": len(final_ir.table_blocks),
            **(doc_user_meta or {}),             # custom business fields attached at ingest
        }
        async with self._postgres.session() as session:
            s6_result = await s6.run(
                chunks=chunks,
                collection_name=collection_id,
                session=session,
                metadata_fields=metadata_fields,
                doc_meta=doc_meta,
            )

        # Flush embed-chain traces onto the document so the inspector can render indexing lineage
        if s6_result.chain_traces:
            async with self._postgres.session() as session:
                current_doc = await self._document_repo.get_by_id(session, doc_id)
                if current_doc is not None:
                    patched_meta = TraceFlusher.build_embed_trace_patch(
                        dict(current_doc.implicit_meta or {}),
                        s6_result.chain_traces,
                    )
                    await self._document_repo.update_status(
                        session, doc_id, current_doc.status, implicit_meta=patched_meta
                    )
        return s6_result

    # ─── Stage resolution ──────────────────────────────────────────────────────

    def _resolve_stages(
        self, pipeline_config: PipelineConfig | None
    ) -> tuple[
        S0IngestStage,
        "_S1ParseStageType",
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

        # 2. Resolve parse chain + S2/S4/S5 from config; wrap parse chain into S1.
        resolved = self._registry.build_stages(pipeline_config)
        s1 = S1ParseStage(parse_chain=resolved.parse_chain, s3=self._s3)

        # 3. Build a per-run S6 from the collection's embed config (overrides injected default)
        s6 = S6Builder.build(pipeline_config.embed, self._qdrant, self._chunk_repo, self._registry)
        return self._s0, s1, resolved.s2, resolved.s4, resolved.s5, s6

    # ─── Parameter extractors ──────────────────────────────────────────────────

    def _s0_params(self, s0: S0IngestStage) -> dict[str, Any]:
        """
        Extract S0 fingerprint parameters from the run's converter.

        These params determine the S0 fingerprint — changing a converter parameter
        (name, version) invalidates the S0 cache for all documents.

        Args:
            s0 (S0IngestStage): The S0 ingest stage whose converter is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (converter name and version).
        """
        return {
            "converter_name": getattr(s0._converter, "name", "gotenberg"),
            "converter_version": getattr(s0._converter, "version", "8"),
        }

    def _s1_params(self, s1: "_S1ParseStageType") -> dict[str, Any]:
        """
        Extract S1 fingerprint parameters from the run's parser.

        Changing parser name, version, or GPU mode invalidates S1 cache entries —
        which is exactly why a different parser backend in the config yields a different
        fingerprint and a fresh parse (the cache stays correct under per-run config).

        Args:
            s1 (_S1ParseStageType): The S1 parse stage whose parser is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (parser name, version, GPU flag).
        """
        # Chain-aware fingerprint: the full signature covers every provider in order
        # so adding/removing/reordering parsers invalidates the cache as expected.
        return {"parse_chain": s1._parse_chain.signature()}

    def _s2_params(self, s2: S2EnrichStage) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters from the run's enrichment stage.

        Delegates to S2EnrichStage.params_for_fingerprint() which returns classifier
        name/version, OCR chain signature, VLM chain signature, and budget cap.
        Changing any of these invalidates the S2 cache for all documents.

        Args:
            s2 (S2EnrichStage): The S2 enrichment stage.

        Returns:
            dict[str, Any]: Fingerprint parameter dict.
        """
        return s2.params_for_fingerprint()
