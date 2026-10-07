# ====== Code Summary ======
# IRApi — the data-access API for the IR domain: the blocks and their detail rows (table / figure),
# plus the enrichments. `persist_ir` inserts a whole document's IR in foreign-key order (blocks →
# details/enrichments), flushing between levels so the self-references (heading tree, caption↔figure)
# and cross-table FKs always resolve.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import BlockType

from ..tables import (
    Block,
    BlockEnrichment,
    BlockFigure,
    BlockTable,
    Document,
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
    ) -> None:
        """
        Persist a document's whole IR in foreign-key order.

        Args:
            session (AsyncSession): The unit of work.
            blocks (Sequence[Block]): The raw IR blocks.
            block_tables (Sequence[BlockTable]): Table detail rows (1:1 with TABLE blocks).
            block_figures (Sequence[BlockFigure]): Figure detail rows (1:1 with FIGURE blocks).
            enrichments (Sequence[BlockEnrichment]): The enrichment results.
        """
        # 1. Blocks first — details, enrichments and self-refs (heading tree, caption) point at them.
        session.add_all(list(blocks))
        await session.flush()
        # 2. Details + enrichments.
        session.add_all([*block_tables, *block_figures, *enrichments])

    @staticmethod
    async def delete_for_document(session: AsyncSession, document_id: uuid.UUID) -> None:
        """Delete a document's IR (cascades details + enrichments) — the re-ingest purge."""
        await session.execute(delete(Block).where(Block.document_id == document_id))

    @staticmethod
    async def get_blocks(session: AsyncSession, document_id: uuid.UUID) -> list[Block]:
        """Return a document's blocks in reading order (the RAW IR)."""
        result = await session.execute(
            select(Block).where(Block.document_id == document_id).order_by(Block.reading_order)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_headings(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[tuple[str | None, int | None, int | None, int]]:
        """
        Return a document's HEADING blocks as (text, level, page, reading_order), in reading order.

        Column-only (no other block, no detail row) — the cheap outline read. ``page`` is None for a
        page-less document (falsy ``page_count``: its blocks carry the placeholder index 0), the same
        rule as the chunk block-location read.

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document whose headings are returned.

        Returns:
            list[tuple[str | None, int | None, int | None, int]]: One row per heading block.
        """
        result = await session.execute(
            select(Block.text, Block.level, Block.page, Block.reading_order, Document.page_count)
            .join(Document, Document.id == Block.document_id)
            .where(Block.document_id == document_id, Block.block_type == BlockType.HEADING.value)
            .order_by(Block.reading_order)
        )
        return [(row[0], row[1], row[2] if row[4] else None, row[3]) for row in result.all()]

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
