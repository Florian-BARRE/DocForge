# ====== Code Summary ======
# Repository for BlockModel: bulk insertion and retrieval of IR blocks for a document.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ir.models import Block, BlockType

# ====== Local Project Imports ======
from ..models import BlockModel


class BlockRepository(LoggerClass):
    """
    Data-access layer for the ``block`` table.

    Converts between IR ``Block`` Pydantic objects and SQLAlchemy ``BlockModel`` rows.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    async def bulk_insert(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        blocks: list[Block],
    ) -> None:
        """
        Persist all IR blocks for a document in a single batched insert.

        Any previously stored blocks for this document are deleted first to
        support idempotent re-runs (same document, re-parsed).

        Args:
            session (AsyncSession): Active transactional session.
            document_id (uuid.UUID): Owning document.
            blocks (list[Block]): All blocks from the DocumentIR, in reading order.
        """
        # 1. Delete existing blocks for this document (idempotent re-run support)
        await session.execute(
            delete(BlockModel).where(BlockModel.document_id == document_id)
        )

        # 2. Map IR blocks → ORM models
        orm_blocks = [self._block_to_model(document_id, b) for b in blocks]

        # 3. Bulk add
        session.add_all(orm_blocks)
        await session.flush()

        self.logger.debug(
            f"Inserted {len(orm_blocks)} blocks for document_id={document_id}"
        )

    async def get_by_document(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> list[BlockModel]:
        """
        Retrieve all blocks for a document, ordered by reading_order.

        Args:
            session (AsyncSession): Active session.
            document_id (uuid.UUID): Owning document.

        Returns:
            list[BlockModel]: All blocks, sorted by reading_order ascending.
        """
        result = await session.execute(
            select(BlockModel)
            .where(BlockModel.document_id == document_id)
            .order_by(BlockModel.reading_order)
        )
        return list(result.scalars().all())

    # ─── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _block_to_model(document_id: uuid.UUID, block: Block) -> BlockModel:
        """
        Convert an IR Block to a BlockModel row.

        Type-specific data (table cells, figure enrichment) is stored in ``type_data`` JSONB.
        """
        # 1. Build type_data payload depending on block type
        type_data: dict = {}
        if block.type == BlockType.TABLE and block.table is not None:
            type_data = block.table.model_dump()
        elif block.type == BlockType.FIGURE and block.figure is not None:
            type_data = block.figure.model_dump()
        # 1b. Carry the chain trace lineage so the UI can render which providers
        # (classifier / OCR / VLM) produced this block's enrichment.  Empty for
        # blocks that no chain touched (text paragraphs etc.).
        if block.chain_traces:
            type_data["chain_traces"] = [t.model_dump() for t in block.chain_traces]

        # 2. Build the ORM row
        return BlockModel(
            id=block.id,
            document_id=document_id,
            type=block.type.value,
            page=block.prov.page,
            bbox=list(block.prov.bbox),
            reading_order=block.reading_order,
            parent_id=block.parent_id,
            level=block.level,
            text=block.text,
            type_data=type_data,
        )
