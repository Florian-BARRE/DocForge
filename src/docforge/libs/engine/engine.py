# ====== Code Summary ======
# StageEngine — P2/P3/P4 pipeline orchestrator with Merkle-DAG fingerprinting and double cache.
# Runs S0 → S1 → S2 → S4 → S5 → S6 with node-level caching for S0/S1/S2.
# S4/S5/S6 use Postgres/Qdrant idempotency instead of the Merkle node cache.
# dry_run mode uses an in-memory node cache and skips all Postgres/Qdrant writes.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.engine.stages.s1_parse import S1ParseStage as _S1ParseStageType
    from libs.core.contracts.pipeline_config import EmbedConfig
    from libs.capabilities.registry import ProviderRegistry

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.models import DocumentIR
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
from libs.capabilities.embed.local.tei import TeiEmbedConfig
from libs.capabilities.embed.local.openai_compat import LocalOpenAIEmbedConfig
from libs.capabilities.embed.external.openai_compat import OpenAIEmbedConfig
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.postgres.repositories import BlockRepository, ChunkRepository, DocumentRepository
from libs.data.storage.qdrant.client import QdrantStorageClient
from libs.data.storage.s3.client import S3Client

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

        # Resolve the effective stage stack: per-run config (via registry) or defaults.
        s0, s1, s2, s4, s5, s6 = self._resolve_stages(pipeline_config)

        # In-memory node cache for dry_run: keyed (doc_id, node_id, fingerprint)
        _local_cache: dict[tuple[str, str, str], str] = {}
        doc_id_str = str(doc_id)

        # 1. Download original bytes if not provided (arq worker path)
        if file_bytes is None:
            original_key = S3Client.key_original(source_hash)
            self.logger.debug(f"Downloading original from S3: {original_key}")
            file_bytes = await self._s3.download(original_key)

        # ── S0 — Ingestion + conversion ─────────────────────────────────────────
        s0_fp = compute_fingerprint(
            node_type="s0",
            code_version=_S0_NODE_VERSION,
            params=self._s0_params(s0),
            input_fingerprints=[source_hash],  # source_hash is the Merkle root
        )

        s0_cache_hit = False
        s0_cached_ref = await self._check_node_cache(
            doc_id, "s0", s0_fp, _local_cache, dry_run
        )

        if s0_cached_ref is not None:
            # S0 cache hit: restore result from S3 meta JSON
            s0_result = await self._restore_s0(s0_cached_ref, doc_id_str)
            s0_cache_hit = True
            self.logger.info(f"S0 cache HIT: doc_id={doc_id}")
        else:
            # S0 cache miss: execute stage, upload meta, store cache entry
            if not dry_run:
                async with self._postgres.session() as session:
                    await self._document_repo.update_status(session, doc_id, "processing")
                    await self._node_cache.start(session, doc_id, "s0", s0_fp)

            try:
                s0_result = await s0.run(
                    file_bytes=file_bytes,
                    filename=filename,
                    doc_id=doc_id_str,
                )
            except Exception as exc:
                if not dry_run:
                    async with self._postgres.session() as session:
                        await self._node_cache.fail(session, doc_id, "s0", s0_fp)
                        await self._document_repo.update_status(session, doc_id, "failed")
                raise

            # Upload S0 output meta JSON to S3
            s0_meta_key = S3Client.key_s0_meta(source_hash, s0_fp)
            await self._s3.upload(
                s0_meta_key,
                self._encode_s0_meta(s0_result),
                "application/json",
            )

            # Commit S0 cache entry
            await self._store_node_cache(doc_id, "s0", s0_fp, s0_meta_key, _local_cache, dry_run)

        # ── S1 — Parse → IR + PNGs + crops ──────────────────────────────────────
        s1_params = self._s1_params(s1)
        s1_fp = compute_fingerprint(
            node_type="s1",
            code_version=_S1_NODE_VERSION,
            params=s1_params,
            input_fingerprints=[s0_fp],
        )

        s1_cache_hit = False
        s1_cached_ref = await self._check_node_cache(
            doc_id, "s1", s1_fp, _local_cache, dry_run
        )

        if s1_cached_ref is not None:
            # S1 cache hit: restore result + download IR from S3
            s1_result, ir = await self._restore_s1(s1_cached_ref)
            s1_cache_hit = True
            self.logger.info(f"S1 cache HIT: doc_id={doc_id}")
        else:
            # S1 cache miss: may need PDF bytes from S0
            if s0_result.pdf_bytes is None:
                # S0 was a cache hit — pdf_bytes are lazy; download from S3 now
                s0_result = await self._populate_pdf_bytes(s0_result)

            if not dry_run:
                async with self._postgres.session() as session:
                    await self._node_cache.start(session, doc_id, "s1", s1_fp)

            try:
                s1_result = await s1.run(s0_result, fingerprint=s1_fp)
            except Exception as exc:
                if not dry_run:
                    async with self._postgres.session() as session:
                        await self._node_cache.fail(session, doc_id, "s1", s1_fp)
                        await self._document_repo.update_status(session, doc_id, "failed")
                raise

            # Upload IR JSON to S3 (content-addressed; reused by cache restore)
            ir = s1_result.ir
            ir_key = S3Client.key_ir(source_hash, s1_fp)
            await self._s3.upload(
                ir_key,
                ir.model_dump_json().encode("utf-8"),
                "application/json",
            )

            # Upload S1 output meta JSON to S3
            s1_meta_key = S3Client.key_s1_meta(source_hash, s1_fp)
            await self._s3.upload(
                s1_meta_key,
                self._encode_s1_meta(s1_result, ir_key),
                "application/json",
            )

            # Commit S1 cache entry
            await self._store_node_cache(doc_id, "s1", s1_fp, s1_meta_key, _local_cache, dry_run)

        # ── S2 — Enrich figures (OCR / VLM / chart-to-data) ─────────────────────
        s2_result: S2Result | None = None
        s2_cache_hit = False
        # final_ir starts as the S1 IR; S2 replaces it with the enriched version
        final_ir = ir

        s2_fp = compute_fingerprint(
            node_type="s2",
            code_version=_S2_NODE_VERSION,
            params=self._s2_params(s2),
            input_fingerprints=[s1_fp],
        )

        s2_cached_ref = await self._check_node_cache(
            doc_id, "s2", s2_fp, _local_cache, dry_run
        )

        if s2_cached_ref is not None:
            # S2 cache hit: restore enriched IR and result stats from S3
            s2_result, final_ir = await self._restore_s2(s2_cached_ref)
            s2_cache_hit = True
            self.logger.info(f"S2 cache HIT: doc_id={doc_id}")
        else:
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

            # Upload the enriched IR to S3 (content-addressed under s2_fp)
            ir_enriched_key = S3Client.key_ir_enriched(source_hash, s2_fp)
            await self._s3.upload(
                ir_enriched_key,
                final_ir.model_dump_json().encode("utf-8"),
                "application/json",
            )

            # Upload the S2 output meta JSON to S3 (node cache artefact)
            s2_meta_key = S3Client.key_s2_meta(source_hash, s2_fp)
            await self._s3.upload(
                s2_meta_key,
                self._encode_s2_meta(s2_result, ir_enriched_key),
                "application/json",
            )

            # Commit S2 cache entry
            await self._store_node_cache(
                doc_id, "s2", s2_fp, s2_meta_key, _local_cache, dry_run
            )

        # ── Persist blocks + finalize document ─────────────────────────────────
        # Use final_ir (enriched when S2 ran, raw S1 IR otherwise) for block storage.
        blocks_already_in_db = s1_cache_hit and (s2_result is None or s2_cache_hit)

        if not dry_run:
            async with self._postgres.session() as session:
                if not blocks_already_in_db:
                    # Bulk-insert only on first run; cache hits mean blocks are already stored
                    await self._block_repo.bulk_insert(
                        session=session,
                        document_id=doc_id,
                        blocks=final_ir.blocks,
                    )
                await self._document_repo.update_status(
                    session,
                    doc_id,
                    "done",
                    page_count=final_ir.n_pages,
                    language=final_ir.language,
                    implicit_meta=self._build_implicit_meta(
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

        # ── S4 — Chunk → S5 — Contextualize → S6 — Embed + Index ───────────────
        # S4 and S5 are PURE transforms over the IR — they run even in dry_run so the
        # playground gets a real chunk preview (spec §5.4).
        # S6 (embed + Qdrant + Postgres persist) only runs in non-dry_run with a collection.
        s4_result: S4Result | None = None
        s5_result: S5Result | None = None
        s6_result: S6Result | None = None

        s4_result = await s4.run(final_ir)
        s5_result = await s5.run(s4_result.chunks, final_ir)
        contextualized_chunks = s5_result.chunks

        if not dry_run and self._chunk_repo is not None:
            if s6 is not None and collection_id is not None:
                # S6 runs the embed+index pipeline and persists chunks internally.
                # Document-level field values (file-intrinsic + derived + user-provided),
                # used by S6 to materialize per-field named vectors + filterable payload (§7.2).
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
                        chunks=contextualized_chunks,
                        collection_name=collection_id,
                        session=session,
                        metadata_fields=metadata_fields,
                        doc_meta=doc_meta,
                    )

                # Flush S6 embed-chain traces onto the document so the inspector can
                # render the indexing lineage (which provider produced which batch).
                if s6_result.chain_traces:
                    async with self._postgres.session() as session:
                        current_doc = await self._document_repo.get_by_id(session, doc_id)
                        if current_doc is not None:
                            current_meta = dict(current_doc.implicit_meta or {})
                            current_meta["embed_chain_traces"] = [
                                t.model_dump() for t in s6_result.chain_traces
                            ]
                            await self._document_repo.update_status(
                                session,
                                doc_id,
                                current_doc.status,
                                implicit_meta=current_meta,
                            )
            elif collection_id is not None:
                # collection_id is set but s6 is unavailable — fail loudly so the user sees the error
                raise RuntimeError(
                    f"S6 indexing required for collection {collection_id!r} "
                    f"but no embed provider / Qdrant is available. "
                    f"Check the collection embed.provider config and QDRANT_HOST connectivity."
                )
            else:
                # No collection → no indexing needed — persist chunks to Postgres only
                async with self._postgres.session() as session:
                    await self._chunk_repo.bulk_insert(session, contextualized_chunks)

        if not dry_run:
            self.logger.info(f"Engine.run done: doc_id={doc_id}")
        else:
            self.logger.info(f"Engine.run dry_run done: doc_id={doc_id}")

        stage_fps: dict[str, str] = {"s0": s0_fp, "s1": s1_fp, "s2": s2_fp}
        cache_flags: dict[str, bool] = {"s0": s0_cache_hit, "s1": s1_cache_hit, "s2": s2_cache_hit}

        budget_spent = s2_result.budget_spent if s2_result is not None else 0.0

        return EngineResult(
            s0_result=s0_result,
            s1_result=s1_result,
            s2_result=s2_result,
            s4_result=s4_result,
            s5_result=s5_result,
            s6_result=s6_result,
            stage_fingerprints=stage_fps,
            from_cache=cache_flags,
            budget_spent=budget_spent,
        )

    # ─── Node cache helpers ────────────────────────────────────────────────────

    async def _check_node_cache(
        self,
        doc_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> str | None:
        """
        Return the cached output_ref, consulting local or DB cache based on mode.

        Args:
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            local_cache (dict): In-memory cache used during dry_run.
            dry_run (bool): When True, consult the in-memory cache instead of Postgres.

        Returns:
            str | None: S3 output_ref on cache hit, or None on miss.
        """
        key = (str(doc_id), node_id, fingerprint)
        if dry_run:
            return local_cache.get(key)
        async with self._postgres.session() as session:
            return await self._node_cache.get(session, doc_id, node_id, fingerprint)

    async def _store_node_cache(
        self,
        doc_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        output_ref: str,
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> None:
        """
        Write the output_ref to the local cache (dry_run) or DB cache (live).

        Args:
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            output_ref (str): S3 key of the node's output artefact to persist.
            local_cache (dict): In-memory cache mutated in place during dry_run.
            dry_run (bool): When True, write to the in-memory cache instead of Postgres.
        """
        key = (str(doc_id), node_id, fingerprint)
        if dry_run:
            local_cache[key] = output_ref
        else:
            async with self._postgres.session() as session:
                await self._node_cache.put(session, doc_id, node_id, fingerprint, output_ref)

    # ─── S0/S1/S2 restore helpers ─────────────────────────────────────────────

    async def _restore_s0(self, s0_meta_key: str, doc_id_str: str) -> S0Result:
        """
        Restore an S0Result from its S3 meta JSON.

        ``pdf_bytes`` is set to None (lazy) and populated by the engine only if S1 is a miss.

        Args:
            s0_meta_key (str): S3 key of the S0 meta JSON artefact.
            doc_id_str (str): Document identifier string (unused in restore; reserved for logging).

        Returns:
            S0Result: Restored S0 result with ``pdf_bytes=None`` (populated lazily on S1 miss).
        """
        raw = await self._s3.download(s0_meta_key)
        meta: dict[str, Any] = json.loads(raw)
        return S0Result(
            doc_id=meta["doc_id"],
            source_hash=meta["source_hash"],
            original_key=meta["original_key"],
            pdf_bytes=None,           # Lazy — downloaded only when S1 is a miss
            pdf_key=meta["pdf_key"],
            page_count=meta["page_count"],
            original_filename=meta["original_filename"],
            original_format=meta["original_format"],
            file_size=meta["file_size"],
            needs_ocr=meta["needs_ocr"],
            implicit_meta=meta["implicit_meta"],
        )

    async def _populate_pdf_bytes(self, s0_result: S0Result) -> S0Result:
        """
        Download PDF bytes from S3 into an S0Result that was restored from cache.

        Args:
            s0_result (S0Result): Cache-restored S0 result with ``pdf_bytes=None``.

        Returns:
            S0Result: A new S0Result identical to the input with ``pdf_bytes`` populated.
        """
        pdf_bytes = await self._s3.download(s0_result.pdf_key)
        return S0Result(
            doc_id=s0_result.doc_id,
            source_hash=s0_result.source_hash,
            original_key=s0_result.original_key,
            pdf_bytes=pdf_bytes,
            pdf_key=s0_result.pdf_key,
            page_count=s0_result.page_count,
            original_filename=s0_result.original_filename,
            original_format=s0_result.original_format,
            file_size=s0_result.file_size,
            needs_ocr=s0_result.needs_ocr,
            implicit_meta=s0_result.implicit_meta,
        )

    async def _restore_s1(self, s1_meta_key: str) -> tuple[S1Result, DocumentIR]:
        """
        Restore an S1Result and DocumentIR from their S3 meta and IR JSON files.

        Args:
            s1_meta_key (str): S3 key of the S1 meta JSON artefact.

        Returns:
            tuple[S1Result, DocumentIR]: Restored S1 result and its associated DocumentIR.
        """
        # 1. Download and parse the S1 meta JSON
        raw = await self._s3.download(s1_meta_key)
        meta: dict[str, Any] = json.loads(raw)

        # 2. Download and reconstruct the DocumentIR from JSON
        ir_raw = await self._s3.download(meta["ir_key"])
        ir = DocumentIR.model_validate_json(ir_raw)

        # 3. Rebuild the S1Result
        s1_result = S1Result(
            ir=ir,
            markdown_key=meta["markdown_key"],
            figure_crop_keys=meta["figure_crop_keys"],
        )
        return s1_result, ir

    async def _restore_s2(self, s2_meta_key: str) -> tuple[S2Result, DocumentIR]:
        """
        Restore an S2Result and enriched DocumentIR from their S3 meta and IR JSON files.

        Args:
            s2_meta_key (str): S3 key of the S2 meta JSON artefact.

        Returns:
            tuple[S2Result, DocumentIR]: Restored S2 result and its enriched DocumentIR.
        """
        # 1. Download and parse the S2 meta JSON
        raw = await self._s3.download(s2_meta_key)
        meta: dict[str, Any] = json.loads(raw)

        # 2. Download and reconstruct the enriched DocumentIR
        ir_raw = await self._s3.download(meta["ir_enriched_key"])
        enriched_ir = DocumentIR.model_validate_json(ir_raw)

        # 3. Rebuild the S2Result from the cached stats
        s2_result = S2Result(
            ir=enriched_ir,
            budget_spent=meta["budget_spent"],
            figures_processed=meta["figures_processed"],
            ocr_calls=meta["ocr_calls"],
            vlm_calls=meta["vlm_calls"],
            chart_extractions=meta["chart_extractions"],
        )
        return s2_result, enriched_ir

    # ─── Serialization helpers ─────────────────────────────────────────────────

    @staticmethod
    def _encode_s0_meta(s0: S0Result) -> bytes:
        """
        Serialize S0Result to a compact JSON blob for S3 storage.

        Args:
            s0 (S0Result): S0 stage output to serialize.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "doc_id": s0.doc_id,
                "source_hash": s0.source_hash,
                "original_key": s0.original_key,
                "pdf_key": s0.pdf_key,
                "page_count": s0.page_count,
                "original_filename": s0.original_filename,
                "original_format": s0.original_format,
                "file_size": s0.file_size,
                "needs_ocr": s0.needs_ocr,
                "implicit_meta": s0.implicit_meta,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _encode_s1_meta(s1: S1Result, ir_key: str) -> bytes:
        """
        Serialize S1Result references to a compact JSON blob for S3 storage.

        Args:
            s1 (S1Result): S1 stage output containing S3 key references.
            ir_key (str): S3 key where the DocumentIR JSON was uploaded.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "ir_key": ir_key,
                "markdown_key": s1.markdown_key,
                "figure_crop_keys": s1.figure_crop_keys,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _encode_s2_meta(s2: S2Result, ir_enriched_key: str) -> bytes:
        """
        Serialize S2Result stats and enriched IR key to a compact JSON blob for S3 storage.

        Args:
            s2 (S2Result): S2 stage output containing enrichment statistics.
            ir_enriched_key (str): S3 key where the enriched DocumentIR JSON was uploaded.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "ir_enriched_key": ir_enriched_key,
                "budget_spent": s2.budget_spent,
                "figures_processed": s2.figures_processed,
                "ocr_calls": s2.ocr_calls,
                "vlm_calls": s2.vlm_calls,
                "chart_extractions": s2.chart_extractions,
            },
            separators=(",", ":"),
        ).encode("utf-8")

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
        from libs.engine.stages.s1_parse import S1ParseStage

        resolved = self._registry.build_stages(pipeline_config)
        s1 = S1ParseStage(parse_chain=resolved.parse_chain, s3=self._s3)

        # 3. Build a per-run S6 from the collection's embed config (overrides injected default)
        s6 = self._build_s6_from_config(pipeline_config.embed)
        return self._s0, s1, resolved.s2, resolved.s4, resolved.s5, s6

    def _build_s6_from_config(self, embed: "EmbedConfig") -> "S6EmbedIndexStage | None":
        """
        Build a per-run S6 stage from the collection's embed provider config.

        Dispatch is handled by a Pydantic discriminated union: the ``embed.provider``
        field resolves to one of the three typed config objects, each of which
        exposes a ``.build()`` method that instantiates the matching provider:

        - ``TeiEmbedConfig``          (``id="tei"``)           → local TEI/BGE-M3, dense + BM25 sparse
        - ``LocalOpenAIEmbedConfig``  (``id="openai_compat"``) → local OpenAI-compat server, dense-only
        - ``OpenAIEmbedConfig``       (``id="openai"``)        → external cloud API, api_key required

        Returns ``None`` when infrastructure (Qdrant or chunk repo) is unavailable — the
        caller raises a ``RuntimeError`` if ``collection_id`` is set (see ``run()``).

        Args:
            embed (EmbedConfig): Collection-level embed configuration (typed provider spec).

        Returns:
            S6EmbedIndexStage | None: A ready S6 stage, or None when infrastructure is missing.
        """
        if self._qdrant is None or self._chunk_repo is None:
            return None

        # Build the embed chain through the registry so every provider in the chain is
        # subject to the same availability + credential checks the other stages enforce.
        if self._registry is None:
            # Fallback when running without a registry (legacy callers): treat the
            # first chain entry as the single provider.
            if not embed.chain:
                return None
            spec = embed.chain[0]
            embed_provider = spec.build()
            batch_size = getattr(spec, "batch_size", 32)
            from libs.capabilities.chain import Chain
            from libs.capabilities.chain_gate import ChainGate
            embed_chain = Chain(stage="embed", providers=[embed_provider], gate=ChainGate(embed.gate))
        else:
            embed_chain = self._registry._build_embed_chain(embed.chain, embed.gate)
            first_spec = embed.chain[0] if embed.chain else None
            batch_size = getattr(first_spec, "batch_size", 32)

        return S6EmbedIndexStage(
            embed_chain=embed_chain,
            qdrant=self._qdrant,
            chunk_repo=self._chunk_repo,
            embed_batch_size=batch_size,
        )

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
        return {
            "parse_chain": s1._parse_chain.signature(),
        }

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

    # ─── Implicit metadata builder ─────────────────────────────────────────────

    @staticmethod
    def _build_implicit_meta(
        s0_result: S0Result,
        ir: DocumentIR,
        s1_result: S1Result,
        s0_fp: str,
        s1_fp: str,
        ir_key: str,
        s2_result: S2Result | None = None,
        s2_fp: str | None = None,
    ) -> dict[str, Any]:
        """
        Assemble the implicit_meta dict for the document record update.

        Combines file-intrinsic S0 metadata with IR-derived statistics and S3 references.
        When S2 ran, enrichment stats (budget_spent, ocr_calls, vlm_calls) are included.

        Args:
            s0_result (S0Result): S0 stage output.
            ir (DocumentIR): Final IR (enriched when S2 ran, raw when S2 skipped).
            s1_result (S1Result): S1 stage output.
            s0_fp (str): S0 Merkle fingerprint.
            s1_fp (str): S1 Merkle fingerprint.
            ir_key (str): S3 key for the (pre-enrichment) DocumentIR JSON.
            s2_result (S2Result | None): S2 stage output, or None when S2 was skipped.
            s2_fp (str | None): S2 Merkle fingerprint, or None when S2 was skipped.

        Returns:
            dict: Implicit metadata dict for the document record.
        """
        meta: dict[str, Any] = {
            **s0_result.implicit_meta,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            "s0_fingerprint": s0_fp,
            "s1_fingerprint": s1_fp,
            "ir_key": ir_key,
            "markdown_key": s1_result.markdown_key,
            # Chain lineage from S1 (parse).  Each entry is a ChainTrace dict ready for the
            # frontend to render: stage, final_provider, attempts[].  Empty when the parse
            # chain was a no-op (single provider, never escalated).
            "chain_traces": [t.model_dump() for t in ir.chain_traces],
            # Parser-side quality estimate (e.g. blocks_with_text / total_blocks).
            # Surfaced in the inspector so operators can see why a chain escalated.
            "quality_score": ir.quality_score,
        }
        if s2_result is not None and s2_fp is not None:
            meta["s2_fingerprint"] = s2_fp
            meta["budget_spent"] = s2_result.budget_spent
            meta["figures_enriched"] = s2_result.figures_processed
            meta["ocr_calls"] = s2_result.ocr_calls
            meta["vlm_calls"] = s2_result.vlm_calls
            meta["chart_extractions"] = s2_result.chart_extractions
            # Provider-call cache statistics so the UI can show how often dedup
            # saved an OCR/VLM/classifier API call across repeating crops.
            meta["ocr_cache_hits"] = s2_result.ocr_cache_hits
            meta["vlm_cache_hits"] = s2_result.vlm_cache_hits
            meta["classifier_calls"] = s2_result.classifier_calls
            meta["classifier_cache_hits"] = s2_result.classifier_cache_hits
            # Enriched IR may have ADDITIONAL chain_traces (none today, but reserve the slot
            # so a future S2-level stage trace can ride here without changing the schema).
            if ir.chain_traces:
                meta["chain_traces"] = [t.model_dump() for t in ir.chain_traces]
        return meta
