# ====== Code Summary ======
# BlobApi — the data-access API for the content-addressed blob registry. `register` is idempotent
# (same content hash → one row). Because blobs are content-addressed they may be SHARED across
# documents; deletion therefore goes through `find_unreferenced` — the multi-reference safety
# filter: given candidate hashes, it returns only those no table references anymore (checked
# against document.source_hash, document.pdf_blob_hash, page.render_blob_hash and
# block_figure.crop_blob_hash), and only those get their S3 object + row removed.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Blob, Block, BlockFigure, Document, Page


class BlobApi:
    """Static data-access API for the blob registry (content-addressed, reference-safe deletion)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def register(session: AsyncSession, blob: Blob) -> Blob:
        """Insert the blob if its content hash is new, else return the existing row (idempotent)."""
        existing = await session.get(Blob, blob.content_hash)
        if existing is not None:
            return existing
        session.add(blob)
        await session.flush()
        return blob

    @staticmethod
    async def get(session: AsyncSession, content_hash: str) -> Blob | None:
        """Fetch a blob by its content hash, or None."""
        return await session.get(Blob, content_hash)

    @staticmethod
    async def collect_hashes_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[str]:
        """Gather every blob hash a document uses — the purge candidates before deleting it."""
        hashes: set[str] = set()
        # 1. The document's own blobs (original + canonical PDF).
        document = await session.get(Document, document_id)
        if document is not None:
            hashes.add(document.source_hash)
            if document.pdf_blob_hash is not None:
                hashes.add(document.pdf_blob_hash)
        # 2. Its page renders and figure crops.
        pages = await session.execute(
            select(Page.render_blob_hash).where(Page.document_id == document_id)
        )
        figures = await session.execute(
            select(BlockFigure.crop_blob_hash)
            .join(Block, BlockFigure.block_id == Block.id)
            .where(Block.document_id == document_id)
        )
        hashes.update(h for h in pages.scalars() if h is not None)
        hashes.update(h for h in figures.scalars() if h is not None)
        return list(hashes)

    @staticmethod
    async def collect_hashes_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[str]:
        """Gather every blob hash a collection's documents use — purge candidates before delete."""
        hashes: set[str] = set()
        # 1. Every document's own blobs.
        documents = await session.execute(
            select(Document.source_hash, Document.pdf_blob_hash).where(
                Document.collection_id == collection_id
            )
        )
        for source_hash, pdf_hash in documents.all():
            hashes.add(source_hash)
            if pdf_hash is not None:
                hashes.add(pdf_hash)
        # 2. Every page render and figure crop, scoped by the collection.
        pages = await session.execute(
            select(Page.render_blob_hash)
            .join(Document, Page.document_id == Document.id)
            .where(Document.collection_id == collection_id)
        )
        figures = await session.execute(
            select(BlockFigure.crop_blob_hash)
            .join(Block, BlockFigure.block_id == Block.id)
            .join(Document, Block.document_id == Document.id)
            .where(Document.collection_id == collection_id)
        )
        hashes.update(h for h in pages.scalars() if h is not None)
        hashes.update(h for h in figures.scalars() if h is not None)
        return list(hashes)

    @staticmethod
    async def find_unreferenced(
        session: AsyncSession, candidate_hashes: Sequence[str]
    ) -> list[str]:
        """
        The multi-reference safety filter: keep only the hashes nothing references anymore.

        Run AFTER a document/collection deletion on the hashes it used — a hash still referenced
        by another document (a shared logo, a re-uploaded file) is filtered out and survives.

        Args:
            session (AsyncSession): The unit of work.
            candidate_hashes (Sequence[str]): Hashes the deleted entity was using.

        Returns:
            list[str]: The subset safe to delete from S3 and the registry.
        """
        if not candidate_hashes:
            return []
        # 1. Collect every hash still referenced by any of the four referencing columns.
        candidates = set(candidate_hashes)
        referencing = (
            select(Document.source_hash).where(Document.source_hash.in_(candidates)),
            select(Document.pdf_blob_hash).where(Document.pdf_blob_hash.in_(candidates)),
            select(Page.render_blob_hash).where(Page.render_blob_hash.in_(candidates)),
            select(BlockFigure.crop_blob_hash).where(BlockFigure.crop_blob_hash.in_(candidates)),
        )
        still_referenced: set[str] = set()
        for statement in referencing:
            result = await session.execute(statement)
            still_referenced.update(hash_ for hash_ in result.scalars() if hash_ is not None)
        # 2. Safe to delete = candidates nothing references anymore.
        return [hash_ for hash_ in candidate_hashes if hash_ not in still_referenced]

    @staticmethod
    async def delete_rows(session: AsyncSession, content_hashes: Sequence[str]) -> None:
        """Remove registry rows — call with `find_unreferenced` output only, after the S3 deletes."""
        if not content_hashes:
            return
        await session.execute(delete(Blob).where(Blob.content_hash.in_(content_hashes)))


__all__ = ["BlobApi"]
