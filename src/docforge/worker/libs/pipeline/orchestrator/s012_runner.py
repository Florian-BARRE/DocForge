# ====== Code Summary ======
# S012Runner — executes the S0/S1/S2 stages with Merkle-DAG node caching.  Each method
# follows the same 4-step pattern: fingerprint → cache check → guarded execute → upload +
# store.  Fingerprint parameter extraction lives in S012ParamHelpers (s012_params.py); the
# start/run/fail guard and final Postgres persistence live in S012PersistHelpers
# (s012_persist.py).  This runner keeps only the 3 caching-interleaved stage methods.
#
# REFACTOR EXCEPTION (>200 lines): the 3 stage methods are structurally parallel but each
# uploads different S3 artefacts (s0: 1 meta; s1: IR + meta; s2: enriched IR + meta) and
# restores via a different codec call, so a single generic method would obscure more than it
# saves.  The overage is dominated by the per-method public-contract docstrings.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.pipeline.stages.s1_parse.core import S1ParseStage as _S1ParseStageType

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.storage.s3.helpers import S3Helpers
from common_libs.pipeline.caches.fingerprint import compute_fingerprint
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage, S0Result
from common_libs.pipeline.stages.s1_parse.core import S1Result
from common_libs.pipeline.stages.s2_enrich import S2EnrichStage, S2Result

# ====== Local Project Imports ======
from .cache_io import CacheIOHelpers
from .deps import StageDeps
from .s012_params import S012ParamHelpers
from .s012_persist import S012PersistHelpers

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

    persist_s012 finalizes the document in Postgres after all three stages complete
    (delegated to S012PersistHelpers).
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
            tuple[S0Result, str, bool]: ``(result, fingerprint, cache_hit)``.

        Note: doc_id/source_hash/local_cache/dry_run carry the same meaning in run_s1/run_s2.
        """
        deps = self._deps
        s0_fp = compute_fingerprint(
            node_type="s0",
            code_version=_S0_NODE_VERSION,
            params=S012ParamHelpers.s0_params(s0),
            input_fingerprints=[source_hash],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s0", s0_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S0 cache HIT: doc_id={doc_id}")
            return await CacheIOHelpers.restore_s0(deps.s3, cached_ref), s0_fp, True

        # 1. Flip document status to ``processing`` on the first real run, then execute S0
        # under the shared start/run/fail guard.
        if not dry_run:
            async with deps.postgres.session() as session:
                await deps.document_repo.update_status(session, doc_id, "processing")
        result = await S012PersistHelpers.guarded_run(
            deps, doc_id, "s0", s0_fp, dry_run,
            lambda: s0.run(file_bytes=file_bytes, filename=filename, doc_id=str(doc_id)),
        )

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
            s0_result (S0Result): Output from the S0 stage (may have lazy pdf_bytes).
            s0_fp (str): S0 Merkle fingerprint (chained as S1 input).
            (doc_id, source_hash, local_cache, dry_run): see run_s0.

        Returns:
            tuple[S1Result, DocumentIR, str, bool]: ``(result, ir, fingerprint, cache_hit)``.
        """
        deps = self._deps
        s1_fp = compute_fingerprint(
            node_type="s1",
            code_version=_S1_NODE_VERSION,
            params=S012ParamHelpers.s1_params(s1),
            input_fingerprints=[s0_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s1", s1_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S1 cache HIT: doc_id={doc_id}")
            s1_result, ir = await CacheIOHelpers.restore_s1(deps.s3, cached_ref)
            return s1_result, ir, s1_fp, True

        # 1. Hydrate pdf_bytes if lazy (S0 was a cache hit), then execute S1 under the guard.
        if s0_result.pdf_bytes is None:
            s0_result = await CacheIOHelpers.populate_pdf_bytes(deps.s3, s0_result)
        hydrated_s0 = s0_result
        s1_result = await S012PersistHelpers.guarded_run(
            deps, doc_id, "s1", s1_fp, dry_run,
            lambda: s1.run(hydrated_s0, fingerprint=s1_fp),
        )

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
            s1_result (S1Result): Output from the S1 stage.
            ir (DocumentIR): DocumentIR produced by S1.
            s1_fp (str): S1 Merkle fingerprint (chained as S2 input).
            (doc_id, source_hash, local_cache, dry_run): see run_s0.

        Returns:
            tuple[S2Result | None, DocumentIR, str, bool]: (result, final_ir, fp, cache_hit).
        """
        deps = self._deps
        s2_fp = compute_fingerprint(
            node_type="s2",
            code_version=_S2_NODE_VERSION,
            params=S012ParamHelpers.s2_params(s2),
            input_fingerprints=[s1_fp],
        )
        cached_ref = await CacheIOHelpers.check(
            deps.postgres, deps.node_cache, doc_id, "s2", s2_fp, local_cache, dry_run
        )
        if cached_ref is not None:
            self.logger.info(f"S2 cache HIT: doc_id={doc_id}")
            s2_result, final_ir = await CacheIOHelpers.restore_s2(deps.s3, cached_ref)
            return s2_result, final_ir, s2_fp, True

        s2_result = await S012PersistHelpers.guarded_run(
            deps, doc_id, "s2", s2_fp, dry_run,
            lambda: s2.run(s1_result, ir),
        )

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
