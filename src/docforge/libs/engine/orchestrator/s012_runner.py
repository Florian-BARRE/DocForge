# ====== Code Summary ======
# S012Runner — executes the S0/S1/S2 stages with Merkle-DAG node caching and persists
# the IR blocks and document status to Postgres.  Extracted from StageEngine.core to
# bring core.py under 200 lines while keeping all S0–S2 logic in one cohesive class.
#
# REFACTOR EXCEPTION (329 lines > 200 limit):
# Each of run_s0/run_s1/run_s2 follows the same 4-step caching pattern (fingerprint →
# cache check → execute → upload+commit) interleaved with async Postgres and S3 calls
# that use self._deps.  Splitting into per-stage files would create 3 tiny files each
# importing the same StageDeps/CacheIOHelpers/TraceFlusher set with no structural gain.
# persist_s012 and the 3 static param extractors are too small to live elsewhere.
# The class is cohesive by design: 1 runner class, 3 caching-interleaved stage methods.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.engine.stages.s1_parse import S1ParseStage as _S1ParseStageType

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.data.storage.s3.helpers import S3Helpers
from libs.engine.fingerprint import compute_fingerprint
from libs.engine.stages.s0_ingest import S0IngestStage, S0Result
from libs.engine.stages.s1_parse import S1Result
from libs.engine.stages.s2_enrich import S2EnrichStage, S2Result

# ====== Local Project Imports ======
from .cache_io import CacheIOHelpers
from .deps import StageDeps
from .trace_flush import TraceFlusher

# ── Node version constants ────────────────────────────────────────────────────
# Increment these when the node's logic changes to invalidate stale cache entries.
_S0_NODE_VERSION: str = "1.0"
_S1_NODE_VERSION: str = "1.0"
_S2_NODE_VERSION: str = "1.0"


class S012Runner(LoggerClass):
    """
    Executes the S0 / S1 / S2 stages with Merkle-DAG node caching.

    Each stage method:
    1. Computes the blake3 fingerprint for the node.
    2. Checks the NodeCache; returns a restored result on cache hit.
    3. Executes the stage, uploads JSON meta to S3, and writes the cache entry.

    _persist_s012 finalizes the document in Postgres after all three stages complete.
    """

    def __init__(self, deps: StageDeps) -> None:
        """
        Initialize with shared infrastructure dependencies.

        Args:
            deps (StageDeps): Frozen container of all shared infra (S3, Postgres, caches, repos).
        """
        LoggerClass.__init__(self)
        self._deps = deps

    # ─── Public stage methods ──────────────────────────────────────────────────

    async def run_s0(
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
        deps = self._deps
        s0_fp = compute_fingerprint(
            node_type="s0",
            code_version=_S0_NODE_VERSION,
            params=self._s0_params(s0),
            input_fingerprints=[source_hash],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s0", s0_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S0 cache HIT: doc_id={doc_id}")
            return await CacheIOHelpers.restore_s0(deps.s3, cached_ref), s0_fp, True

        # 1. Update document status on cache miss (non-dry_run only)
        if not dry_run:
            async with deps.postgres.session() as session:
                await deps.document_repo.update_status(session, doc_id, "processing")
                await deps.node_cache.start(session, doc_id, "s0", s0_fp)
        try:
            result = await s0.run(file_bytes=file_bytes, filename=filename, doc_id=str(doc_id))
        except Exception:
            if not dry_run:
                async with deps.postgres.session() as session:
                    await deps.node_cache.fail(session, doc_id, "s0", s0_fp)
                    await deps.document_repo.update_status(session, doc_id, "failed")
            raise

        # 2. Upload result JSON and record cache entry
        s0_meta_key = S3Helpers.key_s0_meta(source_hash, s0_fp)
        await deps.s3.upload(s0_meta_key, CacheIOHelpers.encode_s0_meta(result), "application/json")
        await CacheIOHelpers.store(
            deps.postgres, deps.node_cache, doc_id, "s0", s0_fp, s0_meta_key, local_cache, dry_run
        )
        return result, s0_fp, False

    async def run_s1(
        self,
        s1: _S1ParseStageType,
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
        deps = self._deps
        s1_fp = compute_fingerprint(
            node_type="s1",
            code_version=_S1_NODE_VERSION,
            params=self._s1_params(s1),
            input_fingerprints=[s0_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s1", s1_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S1 cache HIT: doc_id={doc_id}")
            s1_result, ir = await CacheIOHelpers.restore_s1(deps.s3, cached_ref)
            return s1_result, ir, s1_fp, True

        # 1. Hydrate pdf_bytes if lazy (S0 was a cache hit)
        if s0_result.pdf_bytes is None:
            s0_result = await CacheIOHelpers.populate_pdf_bytes(deps.s3, s0_result)

        if not dry_run:
            async with deps.postgres.session() as session:
                await deps.node_cache.start(session, doc_id, "s1", s1_fp)
        try:
            s1_result = await s1.run(s0_result, fingerprint=s1_fp)
        except Exception:
            if not dry_run:
                async with deps.postgres.session() as session:
                    await deps.node_cache.fail(session, doc_id, "s1", s1_fp)
                    await deps.document_repo.update_status(session, doc_id, "failed")
            raise

        # 2. Upload IR and meta; record cache entry
        ir = s1_result.ir
        ir_key = S3Helpers.key_ir(source_hash, s1_fp)
        await deps.s3.upload(ir_key, ir.model_dump_json().encode("utf-8"), "application/json")
        s1_meta_key = S3Helpers.key_s1_meta(source_hash, s1_fp)
        await deps.s3.upload(
            s1_meta_key, CacheIOHelpers.encode_s1_meta(s1_result, ir_key), "application/json"
        )
        await CacheIOHelpers.store(
            deps.postgres, deps.node_cache, doc_id, "s1", s1_fp, s1_meta_key, local_cache, dry_run
        )
        return s1_result, ir, s1_fp, False

    async def run_s2(
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
        deps = self._deps
        s2_fp = compute_fingerprint(
            node_type="s2",
            code_version=_S2_NODE_VERSION,
            params=self._s2_params(s2),
            input_fingerprints=[s1_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s2", s2_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S2 cache HIT: doc_id={doc_id}")
            s2_result, final_ir = await CacheIOHelpers.restore_s2(deps.s3, cached_ref)
            return s2_result, final_ir, s2_fp, True

        if not dry_run:
            async with deps.postgres.session() as session:
                await deps.node_cache.start(session, doc_id, "s2", s2_fp)
        try:
            s2_result = await s2.run(s1_result, ir)
        except Exception:
            if not dry_run:
                async with deps.postgres.session() as session:
                    await deps.node_cache.fail(session, doc_id, "s2", s2_fp)
                    await deps.document_repo.update_status(session, doc_id, "failed")
            raise

        # 1. Upload enriched IR and meta; record cache entry
        final_ir = s2_result.ir
        ir_enriched_key = S3Helpers.key_ir_enriched(source_hash, s2_fp)
        await deps.s3.upload(
            ir_enriched_key, final_ir.model_dump_json().encode("utf-8"), "application/json"
        )
        s2_meta_key = S3Helpers.key_s2_meta(source_hash, s2_fp)
        await deps.s3.upload(
            s2_meta_key, CacheIOHelpers.encode_s2_meta(s2_result, ir_enriched_key), "application/json"
        )
        await CacheIOHelpers.store(
            deps.postgres, deps.node_cache, doc_id, "s2", s2_fp, s2_meta_key, local_cache, dry_run
        )
        return s2_result, final_ir, s2_fp, False

    async def persist_s012(
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

        deps = self._deps
        # Blocks must only be inserted on the first run; cache hits mean they exist already.
        blocks_already_in_db = s1_cache_hit and (s2_result is None or s2_cache_hit)
        async with deps.postgres.session() as session:
            if not blocks_already_in_db:
                await deps.block_repo.bulk_insert(
                    session=session, document_id=doc_id, blocks=final_ir.blocks
                )
            await deps.document_repo.update_status(
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
                    ir_key=S3Helpers.key_ir(source_hash, s1_fp),
                    s2_result=s2_result,
                    s2_fp=s2_fp,
                ),
            )

    # ─── Parameter extractors ──────────────────────────────────────────────────

    @staticmethod
    def _s0_params(s0: S0IngestStage) -> dict[str, Any]:
        """
        Extract S0 fingerprint parameters from the run's converter.

        Changing a converter parameter (name, version) invalidates the S0 cache
        for all documents.

        Args:
            s0 (S0IngestStage): The S0 ingest stage whose converter is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (converter name and version).
        """
        return {
            "converter_name": getattr(s0._converter, "name", "gotenberg"),
            "converter_version": getattr(s0._converter, "version", "8"),
        }

    @staticmethod
    def _s1_params(s1: _S1ParseStageType) -> dict[str, Any]:
        """
        Extract S1 fingerprint parameters from the run's parser.

        Changing parser name, version, or GPU mode invalidates S1 cache entries.
        The chain-aware fingerprint covers every provider in order so adding/removing/
        reordering parsers invalidates the cache as expected.

        Args:
            s1 (_S1ParseStageType): The S1 parse stage whose parser is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (parse chain signature).
        """
        return {"parse_chain": s1._parse_chain.signature()}

    @staticmethod
    def _s2_params(s2: S2EnrichStage) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters from the run's enrichment stage.

        Delegates to S2EnrichStage.params_for_fingerprint() which returns classifier
        name/version, OCR chain signature, VLM chain signature, and budget cap.

        Args:
            s2 (S2EnrichStage): The S2 enrichment stage.

        Returns:
            dict[str, Any]: Fingerprint parameter dict.
        """
        return s2.params_for_fingerprint()
