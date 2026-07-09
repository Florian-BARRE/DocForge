# ====== Code Summary ======
# DocumentApi — the data-access API for the document domain: the catalogue record, its metadata
# VALUES (document_metadata) and its pages. Includes the dedup lookup (collection + source_hash +
# pipeline_version) and the status transitions the ingestion job drives. Session-driven, Postgres-only.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

from ..tables import Document, DocumentMetadata, DocumentStatus, Page, SourceKind


class DocumentApi:
    """Static data-access API for the document, its metadata values and its pages."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentApi is a static-only class and cannot be instantiated.")

    # -------------------- document --------------------
    @staticmethod
    async def create(session: AsyncSession, document: Document) -> Document:
        """Insert a document and return it (flushed)."""
        session.add(document)
        await session.flush()
        return document

    @staticmethod
    async def get(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
        """Fetch a document by id, or None."""
        return await session.get(Document, document_id)

    @staticmethod
    async def get_by_ids(
        session: AsyncSession, document_ids: Sequence[uuid.UUID]
    ) -> list[Document]:
        """Fetch documents by id — used to resolve a set of chunks back to their collections."""
        if not document_ids:
            return []
        result = await session.execute(select(Document).where(Document.id.in_(document_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def find(
        session: AsyncSession, collection_id: uuid.UUID, source_hash: str, pipeline_version: str
    ) -> Document | None:
        """Dedup lookup: the document with this (collection, source_hash, pipeline_version), or None."""
        result = await session.execute(
            select(Document).where(
                Document.collection_id == collection_id,
                Document.source_hash == source_hash,
                Document.pipeline_version == pipeline_version,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[Document]:
        """Return the documents of a collection, newest first."""
        result = await session.execute(
            select(Document)
            .where(Document.collection_id == collection_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def set_status(
        session: AsyncSession, document_id: uuid.UUID, status: DocumentStatus
    ) -> None:
        """Update a document's ingestion status."""
        document = await session.get(Document, document_id)
        if document is not None:
            document.status = status

    @staticmethod
    async def set_enabled(
        session: AsyncSession, document_id: uuid.UUID, enabled: bool
    ) -> bool:
        """
        Flip a document's searchability toggle (the reversible enable/disable flag).

        A pure Postgres flip — search reads this flag to exclude a disabled document's chunks,
        so no Qdrant point ever has to be touched (no per-chunk fan-out on a doc-level toggle).

        Args:
            session (AsyncSession): The unit of work.
            document_id (uuid.UUID): The document to toggle.
            enabled (bool): The new searchability state.

        Returns:
            bool: Whether the document existed (False → the router raises a 404).
        """
        document = await session.get(Document, document_id)
        if document is None:
            return False
        document.enabled = enabled
        return True

    @staticmethod
    async def list_disabled_ids(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """
        Return the ids of a collection's DISABLED documents — the search exclusion set.

        Bounded by the document count of one collection (not chunks), so the resulting
        ``must_not document_id in {...}`` Qdrant clause stays a single cheap membership filter.
        """
        result = await session.execute(
            select(Document.id).where(
                Document.collection_id == collection_id, Document.enabled.is_(False)
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_facts(
        session: AsyncSession,
        document_id: uuid.UUID,
        *,
        title: str | None = None,
        language: str | None = None,
        page_count: int | None = None,
        source_kind: SourceKind | None = None,
        pdf_blob_hash: str | None = None,
        simhash: str | None = None,
    ) -> None:
        """
        Patch the facts the pipeline LEARNS about a document (None means 'leave unchanged').

        The row is created at admission with only the upload facts; parse/probe later fill the
        title, language, page count, refined source kind, PDF view and near-dup signature.
        """
        document = await session.get(Document, document_id)
        if document is None:
            return
        if title is not None:
            document.title = title
        if language is not None:
            document.language = language
        if page_count is not None:
            document.page_count = page_count
        if source_kind is not None:
            document.source_kind = source_kind
        if pdf_blob_hash is not None:
            document.pdf_blob_hash = pdf_blob_hash
        if simhash is not None:
            document.simhash = simhash

    @staticmethod
    async def delete(session: AsyncSession, document_id: uuid.UUID) -> bool:
        """Delete a document (cascading its blocks, chunks, metadata, pages, jobs); return existence."""
        document = await session.get(Document, document_id)
        if document is None:
            return False
        await session.delete(document)
        return True

    # -------------------- metadata values --------------------
    @staticmethod
    async def get_metadata(
        session: AsyncSession, document_id: uuid.UUID
    ) -> list[DocumentMetadata]:
        """Return the document's metadata values."""
        result = await session.execute(
            select(DocumentMetadata).where(DocumentMetadata.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def replace_metadata(
        session: AsyncSession, document_id: uuid.UUID, values: list[DocumentMetadata]
    ) -> None:
        """
        Replace the document's GENERATED metadata values with ``values``.

        USER-declared rows are written once at admission and must SURVIVE re-ingestion —
        a run's payload only carries generated values, so a blanket delete would wipe the
        declared metadata (and the next re-admission would then reject the document for a
        missing required field — caught in the first real e2e run).
        """
        await session.execute(
            delete(DocumentMetadata).where(
                DocumentMetadata.document_id == document_id,
                DocumentMetadata.origin == FieldOrigin.GENERATED,
            )
        )
        session.add_all(values)

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


__all__ = ["DocumentApi"]
