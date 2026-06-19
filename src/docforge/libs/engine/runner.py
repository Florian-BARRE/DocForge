# ====== Code Summary ======
# P1 pipeline runner: orchestrates S0 → S1 for a single document.
# In P1, execution is synchronous within a FastAPI BackgroundTask.
# In P2, this runner will be replaced by the arq-backed stage engine with Merkle-DAG
# fingerprinting, node cache, provider-call cache, and dry_run support.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.engine.stages.s0_ingest import S0IngestStage
from libs.engine.stages.s1_parse import S1ParseStage
from libs.data.storage.postgres.repositories import BlockRepository, DocumentRepository

if TYPE_CHECKING:
    pass


class PipelineRunner(LoggerClass):
    """
    P1 pipeline runner: S0 → S1 in sequence, within a single async call.

    Responsibilities:
    1. Call S0IngestStage → S0Result (content-address + convert + upload).
    2. Update the document record status to 'processing'.
    3. Call S1ParseStage → S1Result (parse → IR + PNGs + crops + markdown).
    4. Persist the DocumentIR blocks to Postgres.
    5. Update the document record status to 'done' (or 'failed' on error).

    P2 upgrade path: this class will be replaced by an arq task that:
    - Computes Merkle-DAG fingerprints before each stage.
    - Checks the node cache (stage_run table) for hits.
    - Dispatches fan-out micro-tasks for figure enrichment.
    - Supports dry_run mode (ephemeral sink, no Qdrant writes).
    """

    def __init__(
        self,
        s0_stage: S0IngestStage,
        s1_stage: S1ParseStage,
        document_repo: DocumentRepository,
        block_repo: BlockRepository,
    ) -> None:
        """
        Initialize the runner with its stage dependencies.

        Args:
            s0_stage (S0IngestStage): Ingestion and conversion stage.
            s1_stage (S1ParseStage): Parsing and rasterization stage.
            document_repo (DocumentRepository): DB repo for document status updates.
            block_repo (BlockRepository): DB repo for IR block persistence.
        """
        LoggerClass.__init__(self)
        self._s0 = s0_stage
        self._s1 = s1_stage
        self._document_repo = document_repo
        self._block_repo = block_repo

    async def run(
        self,
        session: AsyncSession,
        file_bytes: bytes,
        filename: str,
        doc_id: uuid.UUID,
        pipeline_version: str = "v1",
    ) -> None:
        """
        Execute the full P1 pipeline (S0 → S1) for a single document.

        Updates the document status in Postgres at each step.
        On error, sets status to 'failed' and stores the error message.

        Args:
            session (AsyncSession): Active DB session for status updates.
            file_bytes (bytes): Raw uploaded file bytes.
            filename (str): Original filename.
            doc_id (uuid.UUID): Pre-created document UUID (created by the ingest router).
            pipeline_version (str): Pipeline version label.
        """
        doc_id_str = str(doc_id)

        try:
            # 1. Update document status → processing
            await self._document_repo.update_status(session, doc_id, "processing")

            # 2. S0 — Ingestion + conversion
            self.logger.info(f"Pipeline started: doc_id={doc_id_str} filename={filename!r}")
            s0_result = await self._s0.run(
                file_bytes=file_bytes,
                filename=filename,
                doc_id=doc_id_str,
            )

            # 3. S1 — Parse → IR + PNGs + crops
            s1_result = await self._s1.run(s0_result)

            # 4. Persist IR blocks to Postgres
            await self._block_repo.bulk_insert(
                session=session,
                document_id=doc_id,
                blocks=s1_result.ir.blocks,
            )

            # 5. Update document record with derived metadata
            await self._document_repo.update_status(
                session,
                doc_id,
                "done",
                page_count=s1_result.ir.n_pages,
                language=s1_result.ir.language,
                implicit_meta={
                    **s0_result.implicit_meta,
                    "n_blocks": len(s1_result.ir.blocks),
                    "n_figures": len(s1_result.ir.figure_blocks),
                    "n_tables": len(s1_result.ir.table_blocks),
                    "markdown_key": s1_result.markdown_key,
                    "parser_backend": self._s1._parser.name,
                },
            )

            self.logger.info(f"Pipeline done: doc_id={doc_id_str}")

        except Exception as exc:
            # 6. Mark document as failed and propagate error info
            error_msg = f"{type(exc).__name__}: {exc}"
            self.logger.error(f"Pipeline failed: doc_id={doc_id_str} error={error_msg}")
            try:
                await self._document_repo.update_status(session, doc_id, "failed")
            except Exception:
                pass  # Don't mask the original error
            raise
