# ====== Code Summary ======
# S456Runner — executes the S4/S5/S6 stages (chunk → contextualize → embed + index).
# Extracted from StageEngine.core to bring core.py under 200 lines.
# S4 and S5 always run (pure transforms); S6 runs only in live mode with a collection_id.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipeline.stages.s4_chunk import S4ChunkStage, S4Result
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage, S5Result
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage, S6Result

# ====== Local Project Imports ======
from .deps import StageDeps
from .trace_flush import TraceFlusher


class S456Runner(LoggerClass):
    """
    Executes the S4 / S5 / S6 stages in sequence.

    S4 and S5 are pure IR transforms and always run, even in dry_run (playground needs
    real chunk preview).  S6 is skipped in dry_run or when chunk_repo / collection_id
    are absent; in that case chunks are either discarded (dry_run) or written to Postgres
    without Qdrant indexing.
    """

    def __init__(self, deps: StageDeps) -> None:
        """
        Initialize with shared infrastructure dependencies.

        Args:
            deps (StageDeps): Frozen container of all shared infra (S3, Postgres, caches, repos).
        """
        LoggerClass.__init__(self)
        self._deps = deps

    async def run_s456(
        self,
        s4: S4ChunkStage,
        s5: S5ContextualizeStage,
        s6: S6EmbedIndexStage | None,
        final_ir: Any,
        collection_id: str | None,
        s0_result: Any,
        doc_id: uuid.UUID,
        metadata_fields: list[Any] | None,
        doc_user_meta: dict[str, Any] | None,
        dry_run: bool,
    ) -> tuple[S4Result, S5Result, S6Result | None]:
        """
        Run S4 (chunk) → S5 (contextualize) → S6 (embed + index).

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
        deps = self._deps

        # S4 and S5 always run (pure transforms — playground needs real chunk preview)
        s4_result: S4Result = await s4.run(final_ir)
        s5_result: S5Result = await s5.run(s4_result.chunks, final_ir)
        contextualized_chunks = s5_result.chunks

        s6_result: S6Result | None = None
        if dry_run or deps.chunk_repo is None:
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
            async with deps.postgres.session() as session:
                await deps.chunk_repo.bulk_insert(session, contextualized_chunks)

        return s4_result, s5_result, s6_result

    async def _run_s6_and_flush_traces(
        self,
        s6: S6EmbedIndexStage,
        chunks: list[Any],
        collection_id: str,
        final_ir: Any,
        s0_result: Any,
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
        deps = self._deps
        doc_meta: dict[str, Any] = {
            **(s0_result.implicit_meta or {}),   # filename, extension, file_size, source_hash, page_count, has_scanned_pages
            "language": final_ir.language,       # detected at S1 (py3langid) — filterable system field
            "page_count": final_ir.n_pages,
            "n_blocks": len(final_ir.blocks),
            "n_figures": len(final_ir.figure_blocks),
            "n_tables": len(final_ir.table_blocks),
            **(doc_user_meta or {}),             # custom business fields attached at ingest
        }
        async with deps.postgres.session() as session:
            s6_result = await s6.run(
                chunks=chunks,
                collection_name=collection_id,
                session=session,
                metadata_fields=metadata_fields,
                doc_meta=doc_meta,
            )

        # Flush embed-chain traces onto the document so the inspector can render indexing lineage
        if s6_result.chain_traces:
            async with deps.postgres.session() as session:
                current_doc = await deps.document_repo.get_by_id(session, doc_id)
                if current_doc is not None:
                    patched_meta = TraceFlusher.build_embed_trace_patch(
                        dict(current_doc.implicit_meta or {}),
                        s6_result.chain_traces,
                    )
                    await deps.document_repo.update_status(
                        session, doc_id, current_doc.status, implicit_meta=patched_meta
                    )
        return s6_result
