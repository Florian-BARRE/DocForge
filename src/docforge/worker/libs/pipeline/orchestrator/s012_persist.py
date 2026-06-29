# ====== Code Summary ======
# S012PersistHelpers — persists the document's IR after S0/S1/S2 complete (called from the dynamic
# engine's after-enrich hook). Inserts the IR blocks (only on the first run) and flips the document
# status to ``parsed`` (an intermediate state) with its derived implicit_meta.  The terminal ``done``
# status is only written AFTER S4/S5/S6 succeed, so a document never reads as fully ingested while
# its chunks/vectors are missing.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.storage.s3.helpers import S3Helpers
from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
from common_libs.pipeline.ingest.stages.parsing.result import ParseResult
from common_libs.pipeline.stages.s2_enrich import S2Result

# ====== Local Project Imports ======
from .deps import StageDeps
from .trace_flush import TraceFlusher

_T = TypeVar("_T")


class S012PersistHelpers:
    """
    Static helper that persists IR blocks and finalizes the document record.

    Skips bulk_insert when both S1 and S2 were cache hits (blocks already stored).
    Operates on a shared StageDeps container so it stays decoupled from the runner
    instance.  Also owns ``guarded_run``, the start/run/fail wrapper shared by every
    S0/S1/S2 stage method.
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
        run_stage: Callable[[], Awaitable[_T]],
    ) -> _T:
        """
        Mark the node as ``running``, execute ``run_stage``, and fail loudly on error.

        On any exception the node is marked ``failed`` and the document status is flipped
        to ``failed`` before the exception is re-raised.

        Args:
            deps (StageDeps): Shared infra container (Postgres, node cache, repos).
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (``"s0"`` / ``"s1"`` / ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            run_stage (Callable[[], Awaitable[_T]]): Zero-arg coroutine that runs the stage.

        Returns:
            _T: Whatever ``run_stage`` returns.
        """
        async with deps.postgres.session() as session:
            await deps.node_cache.start(session, doc_id, node_id, fingerprint)
        try:
            return await run_stage()
        except Exception:
            async with deps.postgres.session() as session:
                await deps.node_cache.fail(session, doc_id, node_id, fingerprint)
                await deps.document_repo.update_status(session, doc_id, "failed")
            raise

    @staticmethod
    async def mark_done(deps: StageDeps, doc_id: uuid.UUID) -> None:
        """
        Flip the document to the terminal ``done`` status (success path).

        Called by the engine ONLY after S4/S5/S6 have all succeeded.  Reaching ``done``
        therefore guarantees that the chunks are persisted and — when a collection is set —
        the Qdrant upsert completed.

        Args:
            deps (StageDeps): Shared infra container (Postgres, repos).
            doc_id (uuid.UUID): Document primary key.
        """
        async with deps.postgres.session() as session:
            await deps.document_repo.update_status(session, doc_id, "done")

    @staticmethod
    async def mark_failed(deps: StageDeps, doc_id: uuid.UUID) -> None:
        """
        Flip the document to ``failed`` (failure path), tolerating a DB write error.

        Used by the S4/S5/S6 failure guard.  The status write is wrapped so a secondary
        Postgres failure never masks the ORIGINAL stage error that is being propagated —
        but any such secondary failure is logged loudly (never silently swallowed).

        Args:
            deps (StageDeps): Shared infra container (Postgres, repos).
            doc_id (uuid.UUID): Document primary key.
        """
        try:
            async with deps.postgres.session() as session:
                await deps.document_repo.update_status(session, doc_id, "failed")
        except Exception as exc:  # never mask the original stage error — but log this one
            S012PersistHelpers.logger.error(
                f"Failed to mark document {doc_id} as 'failed' after a stage error: {exc}"
            )

    @classmethod
    async def persist_s012(
        cls,
        deps: StageDeps,
        doc_id: uuid.UUID,
        source_hash: str,
        ingest_result: IngestResult,
        parse_result: ParseResult,
        s1_fp: str,
        s0_fp: str,
        enrich_result: S2Result | None,
        s2_fp: str,
        final_ir: Any,
        s1_cache_hit: bool,
        s2_cache_hit: bool,
    ) -> None:
        """
        Persist IR blocks and update the document record to ``parsed`` in Postgres.

        ``parsed`` is an INTERMEDIATE status: the IR is stored but S4/S5/S6 have not run yet.
        The engine writes the terminal ``done`` only after chunking + (when a collection is
        set) embedding/indexing succeed — so a document can never read as ``done`` while its
        chunks or vectors are missing.

        Skips bulk_insert when both S1 and S2 were cache hits (blocks already stored).

        Args:
            deps (StageDeps): Frozen container of all shared infra (Postgres, repos).
            doc_id (uuid.UUID): Document primary key.
            source_hash (str): SHA-256 of the original file (used to derive S3 key).
            ingest_result (IngestResult): S0 output (contributes to implicit_meta).
            parse_result (ParseResult): S1 output (contributes markdown_key to implicit_meta).
            s1_fp (str): S1 Merkle fingerprint.
            s0_fp (str): S0 Merkle fingerprint.
            enrich_result (S2Result | None): S2 output, or None when S2 was skipped.
            s2_fp (str): S2 Merkle fingerprint.
            final_ir (DocumentIR): Enriched IR (or raw S1 IR when S2 skipped).
            s1_cache_hit (bool): True when S1 was a cache hit (blocks already stored).
            s2_cache_hit (bool): True when S2 was a cache hit.
        """
        # Blocks must only be inserted on the first run; cache hits mean they exist already.
        blocks_already_in_db = s1_cache_hit and (enrich_result is None or s2_cache_hit)
        async with deps.postgres.session() as session:
            if not blocks_already_in_db:
                await deps.block_repo.bulk_insert(
                    session=session, document_id=doc_id, blocks=final_ir.blocks
                )
            await deps.document_repo.update_status(
                session,
                doc_id,
                "parsed",
                page_count=final_ir.n_pages,
                language=final_ir.language,
                implicit_meta=TraceFlusher.build_implicit_meta(
                    ingest_result=ingest_result,
                    ir=final_ir,
                    parse_result=parse_result,
                    s0_fp=s0_fp,
                    s1_fp=s1_fp,
                    ir_key=S3Helpers.key_ir(source_hash, s1_fp),
                    enrich_result=enrich_result,
                    s2_fp=s2_fp,
                ),
            )


# ------------------- Public API ------------------- #
__all__ = ["S012PersistHelpers"]
