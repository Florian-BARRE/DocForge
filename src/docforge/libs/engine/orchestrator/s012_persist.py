# ====== Code Summary ======
# S012PersistHelpers — finalizes a document in Postgres after S0/S1/S2 complete.
# Inserts the IR blocks (only on the first run) and flips the document status to ``done``
# with its derived implicit_meta.  Extracted from S012Runner to keep the runner focused on
# the per-stage caching pattern.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.data.storage.s3.helpers import S3Helpers
from libs.engine.stages.s0_ingest import S0Result
from libs.engine.stages.s1_parse import S1Result
from libs.engine.stages.s2_enrich import S2Result

# ====== Local Project Imports ======
from .deps import StageDeps
from .trace_flush import TraceFlusher

_T = TypeVar("_T")


class S012PersistHelpers:
    """
    Static helper that persists IR blocks and finalizes the document record.

    Skips bulk_insert when both S1 and S2 were cache hits (blocks already stored).
    No-op in dry_run mode.  Operates on a shared StageDeps container so it stays
    decoupled from the runner instance.  Also owns ``guarded_run``, the start/run/fail
    wrapper shared by every S0/S1/S2 stage method.
    """

    logger = loggerplusplus.bind(identifier="S012PersistHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("S012PersistHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    async def guarded_run(
        deps: StageDeps,
        doc_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        dry_run: bool,
        run_stage: Callable[[], Awaitable[_T]],
    ) -> _T:
        """
        Mark the node as ``running``, execute ``run_stage``, and fail loudly on error.

        On any exception (non-dry_run) the node is marked ``failed`` and the document status
        is flipped to ``failed`` before the exception is re-raised.

        Args:
            deps (StageDeps): Shared infra container (Postgres, node cache, repos).
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (``"s0"`` / ``"s1"`` / ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            dry_run (bool): When True, skip all Postgres writes.
            run_stage (Callable[[], Awaitable[_T]]): Zero-arg coroutine that runs the stage.

        Returns:
            _T: Whatever ``run_stage`` returns.
        """
        if not dry_run:
            async with deps.postgres.session() as session:
                await deps.node_cache.start(session, doc_id, node_id, fingerprint)
        try:
            return await run_stage()
        except Exception:
            if not dry_run:
                async with deps.postgres.session() as session:
                    await deps.node_cache.fail(session, doc_id, node_id, fingerprint)
                    await deps.document_repo.update_status(session, doc_id, "failed")
            raise

    @classmethod
    async def persist_s012(
        cls,
        deps: StageDeps,
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
            deps (StageDeps): Frozen container of all shared infra (Postgres, repos).
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


# ------------------- Public API ------------------- #
__all__ = ["S012PersistHelpers"]
