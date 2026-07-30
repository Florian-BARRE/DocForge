# ====== Code Summary ======
# IRApi — the data-access API for the IR domain: the blocks and their detail rows (table / figure),
# plus the enrichments and their attempt traces. `persist_ir` inserts a whole document's IR in
# foreign-key order (blocks → details/enrichments → attempts), flushing between levels so the
# self-references (heading tree, caption↔figure) and cross-table FKs always resolve.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import (
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    EnrichmentAttempt,
)


class IRApi:
    """Static data-access API for the blocks, their details, and their enrichments."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IRApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def persist_ir(
        session: AsyncSession,
        blocks: Sequence[Block],
        *,
        block_tables: Sequence[BlockTable] = (),
        block_figures: Sequence[BlockFigure] = (),
        enrichments: Sequence[BlockEnrichment] = (),
        attempts: Sequence[EnrichmentAttempt] = (),
    ) -> None:
        """
        Persist a document's whole IR in foreign-key order.

        Args:
            session (AsyncSession): The unit of work.
            blocks (Sequence[Block]): The raw IR blocks.
            block_tables (Sequence[BlockTable]): Table detail rows (1:1 with TABLE blocks).
            block_figures (Sequence[BlockFigure]): Figure detail rows (1:1 with FIGURE blocks).
            enrichments (Sequence[BlockEnrichment]): The enrichment results.
            attempts (Sequence[EnrichmentAttempt]): The enrichment model-chain traces.
        """
        # 1. Blocks first — details, enrichments and self-refs (heading tree, caption) point at them.
        session.add_all(list(blocks))
        await session.flush()
        # 2. Details + enrichments — attempts point at the enrichments.
        session.add_all([*block_tables, *block_figures, *enrichments])
        await session.flush()
        # 3. The enrichment traces.
        session.add_all(list(attempts))

    @staticmethod
    async def delete_for_document(session: AsyncSession, document_id: uuid.UUID) -> None:
        """Delete a document's IR (cascades details, enrichments, attempts) — the re-ingest purge."""
        await session.execute(delete(Block).where(Block.document_id == document_id))

    @staticmethod
    async def get_blocks(session: AsyncSession, document_id: uuid.UUID) -> list[Block]:
        """Return a document's blocks in reading order (the RAW IR)."""
        result = await session.execute(
            select(Block).where(Block.document_id == document_id).order_by(Block.reading_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_tables(session: AsyncSession, document_id: uuid.UUID) -> list[BlockTable]:
        """Return a document's table detail rows (joined through their blocks)."""
        result = await session.execute(
            select(BlockTable)
            .join(Block, BlockTable.block_id == Block.id)
            .where(Block.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_figures(session: AsyncSession, document_id: uuid.UUID) -> list[BlockFigure]:
        """Return a document's figure detail rows (joined through their blocks)."""
        result = await session.execute(
            select(BlockFigure)
            .join(Block, BlockFigure.block_id == Block.id)
            .where(Block.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_document_enrichments(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[BlockEnrichment]:
        """Return every enrichment of a document (the ENRICHED IR, for inspection/assembly)."""
        result = await session.execute(
            select(BlockEnrichment)
            .join(Block, BlockEnrichment.block_id == Block.id)
            .where(Block.document_id == document_id)
        )
        return list(result.scalars().all())


__all__ = ["IRApi"]
