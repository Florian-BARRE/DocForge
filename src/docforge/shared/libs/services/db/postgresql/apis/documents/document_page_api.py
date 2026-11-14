# ====== Code Summary ======
# DocumentPageApi — the data-access API for a document's pages: the idempotent replace on
# re-ingest and the ordered read. Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import Page


class DocumentPageApi:
    """Static data-access API for a document's pages."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentPageApi is a static-only class and cannot be instantiated.")

    # -------------------- pages --------------------
    @staticmethod
    async def replace_pages(
        session: AsyncSession, document_id: uuid.UUID, pages: list[Page]
    ) -> None:
        """Replace a document's pages (idempotent on re-ingest)."""
        await session.execute(delete(Page).where(Page.document_id == document_id))
        session.add_all(pages)

    @staticmethod
    async def get_pages(session: AsyncSession, document_id: uuid.UUID) -> list[Page]:
        """Return a document's pages, in order."""
        result = await session.execute(
            select(Page).where(Page.document_id == document_id).order_by(Page.page_number)
        )
        return list(result.scalars().all())


__all__ = ["DocumentPageApi"]
